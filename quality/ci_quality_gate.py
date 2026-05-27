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


QualityStatus = Literal["PASS", "WARN", "FAIL", "SKIP"]
QualitySeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class QualityGateConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/quality")
    output_file: Path = Path("artifacts/quality/quality_gate_report.json")

    require_tests: bool = True
    require_runtime_config: bool = True
    require_failure_injection: bool = True
    require_security_audit: bool = True
    require_import_smoke: bool = True


class QualityCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    check_id: str
    name: str
    status: QualityStatus
    severity: QualitySeverity = "HIGH"

    command: list[str] = Field(default_factory=list)
    returncode: int | None = None

    stdout: str = ""
    stderr: str = ""

    blocking: bool = True
    duration_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityGateReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "ci_quality_gate"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: QualityStatus

    checks_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    skip_count: int
    blocking_fail_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    checks: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_quality_gate_config() -> QualityGateConfig:
    return QualityGateConfig(
        output_dir=Path(os.getenv("QUALITY_OUTPUT_DIR", "artifacts/quality")),
        output_file=Path(os.getenv("QUALITY_GATE_OUTPUT_FILE", "artifacts/quality/quality_gate_report.json")),
        require_tests=env_bool("QUALITY_REQUIRE_TESTS", True),
        require_runtime_config=env_bool("QUALITY_REQUIRE_RUNTIME_CONFIG", True),
        require_failure_injection=env_bool("QUALITY_REQUIRE_FAILURE_INJECTION", True),
        require_security_audit=env_bool("QUALITY_REQUIRE_SECURITY_AUDIT", True),
        require_import_smoke=env_bool("QUALITY_REQUIRE_IMPORT_SMOKE", True),
    )


def build_quality_check_from_command(
    *,
    check_id: str,
    name: str,
    command: list[str],
    severity: QualitySeverity = "HIGH",
    blocking: bool = True,
    timeout_seconds: int = 300,
) -> QualityCheck:
    started = datetime.now(timezone.utc)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr

    except subprocess.TimeoutExpired as exc:
        duration = (datetime.now(timezone.utc) - started).total_seconds()

        return QualityCheck(
            check_id=check_id,
            name=name,
            status="FAIL",
            severity=severity,
            command=command,
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or str(exc),
            blocking=blocking,
            duration_seconds=round(duration, 4),
            metadata={"error": "timeout"},
        )

    except OSError as exc:
        duration = (datetime.now(timezone.utc) - started).total_seconds()

        return QualityCheck(
            check_id=check_id,
            name=name,
            status="FAIL",
            severity=severity,
            command=command,
            returncode=None,
            stderr=str(exc),
            blocking=blocking,
            duration_seconds=round(duration, 4),
            metadata={"error": "os_error"},
        )

    duration = (datetime.now(timezone.utc) - started).total_seconds()

    return QualityCheck(
        check_id=check_id,
        name=name,
        status="PASS" if returncode == 0 else "FAIL",
        severity=severity,
        command=command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        blocking=blocking,
        duration_seconds=round(duration, 4),
    )


def evaluate_quality_gate(
    *,
    checks: list[QualityCheck | dict[str, Any]],
    config: QualityGateConfig | None = None,
) -> QualityGateReport:
    resolved_config = config or load_quality_gate_config()

    parsed = [
        item if isinstance(item, QualityCheck) else QualityCheck.model_validate(item)
        for item in checks
    ]

    pass_count = sum(1 for item in parsed if item.status == "PASS")
    warn_count = sum(1 for item in parsed if item.status == "WARN")
    fail_count = sum(1 for item in parsed if item.status == "FAIL")
    skip_count = sum(1 for item in parsed if item.status == "SKIP")
    blocking_fail_count = sum(1 for item in parsed if item.status == "FAIL" and item.blocking)

    blockers = [item.check_id for item in parsed if item.status == "FAIL" and item.blocking]
    warnings = [item.check_id for item in parsed if item.status in {"WARN", "SKIP"} or (item.status == "FAIL" and not item.blocking)]

    passed = blocking_fail_count == 0

    return QualityGateReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        checks_count=len(parsed),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        skip_count=skip_count,
        blocking_fail_count=blocking_fail_count,
        blockers=blockers,
        warnings=warnings,
        checks=[item.model_dump(mode="json") for item in parsed],
        config=resolved_config.model_dump(mode="json"),
    )


def export_quality_gate_report(
    report: QualityGateReport,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_quality_gate_config()
    output_path = Path(path or config.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def default_quality_commands() -> list[dict[str, Any]]:
    return [
        {
            "check_id": "pytest_full",
            "name": "Full pytest suite",
            "command": ["python", "-m", "pytest"],
            "severity": "CRITICAL",
            "blocking": True,
            "timeout_seconds": 900,
        },
        {
            "check_id": "runtime_config_validation",
            "name": "Runtime config validation",
            "command": ["python", "scripts/run_runtime_config_validation.py", "--export", "--name", "ci_runtime_config"],
            "severity": "HIGH",
            "blocking": True,
            "timeout_seconds": 120,
        },
        {
            "check_id": "failure_injection",
            "name": "Failure injection safety test",
            "command": ["python", "scripts/run_failure_injection.py", "--export", "--name", "ci_failure_injection"],
            "severity": "HIGH",
            "blocking": True,
            "timeout_seconds": 120,
        },
        {
            "check_id": "security_audit_scoped",
            "name": "Scoped security audit",
            "command": ["python", "-u", "scripts/run_security_audit.py", "--export", "--scan-root", "security"],
            "severity": "HIGH",
            "blocking": True,
            "timeout_seconds": 180,
        },
        {
            "check_id": "import_smoke",
            "name": "Critical import smoke check",
            "command": [
                "python",
                "-c",
                "from infra.runtime_config_validator import validate_runtime_config; from observability.metrics_registry import build_metrics_snapshot; from security.environment_policy import evaluate_environment_policy; print('import smoke OK')",
            ],
            "severity": "HIGH",
            "blocking": True,
            "timeout_seconds": 60,
        },
    ]