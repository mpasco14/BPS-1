from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


VulnerabilitySeverity = Literal["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
DependencyAuditStatus = Literal["PASS", "WARN", "FAIL"]


class DependencySecurityAuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/security")

    fail_on_critical: bool = True
    fail_on_high: bool = True

    max_high: int = 0
    max_medium: int = 5


class DependencyVulnerability(BaseModel):
    model_config = ConfigDict(extra="allow")

    package: str
    installed_version: str | None = None
    vulnerability_id: str
    severity: VulnerabilitySeverity = "UNKNOWN"

    summary: str | None = None
    fixed_versions: list[str] = Field(default_factory=list)
    source: str = "manual"


class DependencySecurityAuditReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "dependency_security_audit"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: DependencyAuditStatus

    vulnerabilities_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    unknown_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    vulnerabilities: list[dict[str, Any]] = Field(default_factory=list)
    command_result: dict[str, Any] | None = None
    config: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_dependency_security_audit_config() -> DependencySecurityAuditConfig:
    return DependencySecurityAuditConfig(
        output_dir=Path(os.getenv("DEPENDENCY_SECURITY_OUTPUT_DIR", "artifacts/security")),
        fail_on_critical=env_bool("DEPENDENCY_SECURITY_FAIL_ON_CRITICAL", True),
        fail_on_high=env_bool("DEPENDENCY_SECURITY_FAIL_ON_HIGH", True),
        max_high=env_int("DEPENDENCY_SECURITY_MAX_HIGH", 0),
        max_medium=env_int("DEPENDENCY_SECURITY_MAX_MEDIUM", 5),
    )


def normalize_severity(value: str | None) -> VulnerabilitySeverity:
    if not value:
        return "UNKNOWN"

    normalized = value.strip().upper()

    if normalized in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        return normalized  # type: ignore[return-value]

    return "UNKNOWN"


def vulnerabilities_from_pip_audit_json(payload: dict[str, Any]) -> list[DependencyVulnerability]:
    vulnerabilities: list[DependencyVulnerability] = []

    for dependency in payload.get("dependencies", []):
        package = dependency.get("name", "unknown")
        version = dependency.get("version")

        for vuln in dependency.get("vulns", []):
            aliases = vuln.get("aliases") or []
            vulnerability_id = vuln.get("id") or (aliases[0] if aliases else "unknown")

            vulnerabilities.append(
                DependencyVulnerability(
                    package=package,
                    installed_version=version,
                    vulnerability_id=vulnerability_id,
                    severity=normalize_severity(vuln.get("severity")),
                    summary=vuln.get("description") or vuln.get("summary"),
                    fixed_versions=vuln.get("fix_versions") or [],
                    source="pip-audit",
                )
            )

    return vulnerabilities


def run_dependency_audit_command(
    *,
    command: list[str] | None = None,
    timeout_seconds: int = 60,
) -> tuple[list[DependencyVulnerability], dict[str, Any]]:
    resolved_command = command or ["python", "-m", "pip_audit", "--format", "json"]

    try:
        completed = subprocess.run(
            resolved_command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], {
            "command": resolved_command,
            "returncode": None,
            "error": str(exc),
            "stdout": "",
            "stderr": "",
        }

    command_result = {
        "command": resolved_command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return [], command_result

    return vulnerabilities_from_pip_audit_json(payload), command_result


def build_dependency_security_audit_report(
    *,
    vulnerabilities: list[DependencyVulnerability | dict[str, Any]] | None = None,
    command_result: dict[str, Any] | None = None,
    config: DependencySecurityAuditConfig | None = None,
) -> DependencySecurityAuditReport:
    resolved_config = config or load_dependency_security_audit_config()

    parsed = [
        item if isinstance(item, DependencyVulnerability) else DependencyVulnerability.model_validate(item)
        for item in (vulnerabilities or [])
    ]

    critical = sum(1 for item in parsed if item.severity == "CRITICAL")
    high = sum(1 for item in parsed if item.severity == "HIGH")
    medium = sum(1 for item in parsed if item.severity == "MEDIUM")
    low = sum(1 for item in parsed if item.severity == "LOW")
    unknown = sum(1 for item in parsed if item.severity == "UNKNOWN")

    blockers: list[str] = []
    warnings: list[str] = []

    if resolved_config.fail_on_critical and critical > 0:
        blockers.append("critical_vulnerabilities_present")

    if resolved_config.fail_on_high and high > resolved_config.max_high:
        blockers.append("high_vulnerabilities_above_limit")

    if medium > resolved_config.max_medium:
        warnings.append("medium_vulnerabilities_above_limit")

    if unknown > 0:
        warnings.append("unknown_severity_vulnerabilities_present")

    passed = not blockers

    return DependencySecurityAuditReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        vulnerabilities_count=len(parsed),
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
        unknown_count=unknown,
        blockers=blockers,
        warnings=warnings,
        vulnerabilities=[item.model_dump(mode="json") for item in parsed],
        command_result=command_result,
        config=resolved_config.model_dump(mode="json"),
    )


def export_dependency_security_audit_report(
    report: DependencySecurityAuditReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "dependency_security_audit_latest",
) -> Path:
    config = load_dependency_security_audit_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path