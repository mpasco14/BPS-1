from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


PermissionAuditStatus = Literal["PASS", "WARN", "FAIL"]
PermissionSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class ApiPermissionAuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/security")

    require_read: bool = True
    require_trade: bool = True
    require_futures: bool = True
    require_ip_restriction: bool = False

    forbid_withdrawal: bool = True
    forbid_transfer: bool = True


class ApiKeyPermissionRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    key_name: str
    present: bool = True

    read_enabled: bool = True
    trade_enabled: bool = True
    futures_enabled: bool = True
    spot_enabled: bool = False
    withdrawal_enabled: bool = False
    transfer_enabled: bool = False
    margin_enabled: bool = False

    ip_restricted: bool = False
    allowed_ips: list[str] = Field(default_factory=list)

    environment: str = "testnet"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApiPermissionFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    severity: PermissionSeverity
    message: str
    key_name: str
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class ApiPermissionAuditReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "api_permission_audit"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: PermissionAuditStatus

    keys_count: int
    findings_count: int
    critical_count: int
    high_count: int
    blocking_findings_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    findings: list[dict[str, Any]] = Field(default_factory=list)
    keys: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_api_permission_audit_config() -> ApiPermissionAuditConfig:
    return ApiPermissionAuditConfig(
        output_dir=Path(os.getenv("API_PERMISSION_AUDIT_OUTPUT_DIR", "artifacts/security")),
        require_read=env_bool("API_PERMISSION_REQUIRE_READ", True),
        require_trade=env_bool("API_PERMISSION_REQUIRE_TRADE", True),
        require_futures=env_bool("API_PERMISSION_REQUIRE_FUTURES", True),
        require_ip_restriction=env_bool("API_PERMISSION_REQUIRE_IP_RESTRICTION", False),
        forbid_withdrawal=env_bool("API_PERMISSION_FORBID_WITHDRAWAL", True),
        forbid_transfer=env_bool("API_PERMISSION_FORBID_TRANSFER", True),
    )


def finding(
    *,
    code: str,
    severity: PermissionSeverity,
    message: str,
    key_name: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> ApiPermissionFinding:
    return ApiPermissionFinding(
        code=code,
        severity=severity,
        message=message,
        key_name=key_name,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def audit_api_key_permissions(
    key: ApiKeyPermissionRecord,
    *,
    config: ApiPermissionAuditConfig,
) -> list[ApiPermissionFinding]:
    findings: list[ApiPermissionFinding] = []

    if not key.present:
        findings.append(
            finding(
                code="api_key_missing",
                severity="CRITICAL",
                message="API key ausente.",
                key_name=key.key_name,
                value=False,
                expected=True,
                blocking=True,
            )
        )

    if config.require_read and not key.read_enabled:
        findings.append(
            finding(
                code="read_permission_missing",
                severity="HIGH",
                message="Permissão de leitura ausente.",
                key_name=key.key_name,
                value=False,
                expected=True,
                blocking=True,
            )
        )

    if config.require_trade and not key.trade_enabled:
        findings.append(
            finding(
                code="trade_permission_missing",
                severity="HIGH",
                message="Permissão de trade ausente.",
                key_name=key.key_name,
                value=False,
                expected=True,
                blocking=True,
            )
        )

    if config.require_futures and not key.futures_enabled:
        findings.append(
            finding(
                code="futures_permission_missing",
                severity="HIGH",
                message="Permissão de futures ausente.",
                key_name=key.key_name,
                value=False,
                expected=True,
                blocking=True,
            )
        )

    if config.require_ip_restriction and not key.ip_restricted:
        findings.append(
            finding(
                code="ip_restriction_missing",
                severity="HIGH",
                message="API key sem restrição de IP.",
                key_name=key.key_name,
                value=False,
                expected=True,
                blocking=True,
            )
        )

    if key.spot_enabled:
        findings.append(
            finding(
                code="spot_permission_enabled",
                severity="LOW",
                message="Permissão spot habilitada; não é necessária para este bot.",
                key_name=key.key_name,
                value=True,
                expected=False,
                blocking=False,
            )
        )

    if key.margin_enabled:
        findings.append(
            finding(
                code="margin_permission_enabled",
                severity="MEDIUM",
                message="Permissão margin habilitada; revisar necessidade.",
                key_name=key.key_name,
                value=True,
                expected=False,
                blocking=False,
            )
        )

    if config.forbid_withdrawal and key.withdrawal_enabled:
        findings.append(
            finding(
                code="withdrawal_permission_enabled",
                severity="CRITICAL",
                message="Permissão de saque habilitada. Nunca usar em trading bot.",
                key_name=key.key_name,
                value=True,
                expected=False,
                blocking=True,
            )
        )

    if config.forbid_transfer and key.transfer_enabled:
        findings.append(
            finding(
                code="transfer_permission_enabled",
                severity="CRITICAL",
                message="Permissão de transferência habilitada. Nunca usar em trading bot.",
                key_name=key.key_name,
                value=True,
                expected=False,
                blocking=True,
            )
        )

    return findings


def build_api_permission_audit_report(
    *,
    keys: list[ApiKeyPermissionRecord | dict[str, Any]],
    config: ApiPermissionAuditConfig | None = None,
) -> ApiPermissionAuditReport:
    resolved_config = config or load_api_permission_audit_config()

    parsed_keys = [
        item if isinstance(item, ApiKeyPermissionRecord) else ApiKeyPermissionRecord.model_validate(item)
        for item in keys
    ]

    findings: list[ApiPermissionFinding] = []

    for key in parsed_keys:
        findings.extend(audit_api_key_permissions(key, config=resolved_config))

    critical = sum(1 for item in findings if item.severity == "CRITICAL")
    high = sum(1 for item in findings if item.severity == "HIGH")
    blocking = [item for item in findings if item.blocking]

    blockers = [f"{item.key_name}:{item.code}" for item in blocking]
    warnings = [f"{item.key_name}:{item.code}" for item in findings if not item.blocking]

    passed = not blockers

    return ApiPermissionAuditReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        keys_count=len(parsed_keys),
        findings_count=len(findings),
        critical_count=critical,
        high_count=high,
        blocking_findings_count=len(blocking),
        blockers=blockers,
        warnings=warnings,
        findings=[item.model_dump(mode="json") for item in findings],
        keys=[item.model_dump(mode="json") for item in parsed_keys],
        config=resolved_config.model_dump(mode="json"),
    )


def export_api_permission_audit_report(
    report: ApiPermissionAuditReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "api_permission_audit_latest",
) -> Path:
    config = load_api_permission_audit_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path