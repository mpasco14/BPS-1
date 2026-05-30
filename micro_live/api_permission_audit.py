from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live.common import env_bool, export_json


PermissionAuditStatus = Literal["PASS", "WARN", "FAIL"]


class LiveAPIPermissionAuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/micro_live")

    futures_trading_permission: bool = True
    withdrawals_permission: bool = False
    universal_transfer_permission: bool = False
    ip_restricted: bool = True
    read_only: bool = False

    require_futures_trading_permission: bool = True
    require_withdrawals_disabled: bool = True
    require_universal_transfer_disabled: bool = True
    require_ip_restriction: bool = True


class LiveAPIPermissionAuditReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_live_api_permission_audit"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: PermissionAuditStatus
    passed: bool

    futures_trading_permission: bool
    withdrawals_permission: bool
    universal_transfer_permission: bool
    ip_restricted: bool
    read_only: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    config: dict[str, Any]


def load_live_api_permission_audit_config() -> LiveAPIPermissionAuditConfig:
    return LiveAPIPermissionAuditConfig(
        output_dir=Path(os.getenv("MICRO_LIVE_OUTPUT_DIR", "artifacts/micro_live")),
        futures_trading_permission=env_bool("MICRO_LIVE_PERMISSION_FUTURES_TRADING", True),
        withdrawals_permission=env_bool("MICRO_LIVE_PERMISSION_WITHDRAWALS", False),
        universal_transfer_permission=env_bool("MICRO_LIVE_PERMISSION_UNIVERSAL_TRANSFER", False),
        ip_restricted=env_bool("MICRO_LIVE_PERMISSION_IP_RESTRICTED", True),
        read_only=env_bool("MICRO_LIVE_PERMISSION_READ_ONLY", False),
        require_futures_trading_permission=env_bool("MICRO_LIVE_REQUIRE_FUTURES_TRADING_PERMISSION", True),
        require_withdrawals_disabled=env_bool("MICRO_LIVE_REQUIRE_WITHDRAWALS_DISABLED", True),
        require_universal_transfer_disabled=env_bool("MICRO_LIVE_REQUIRE_UNIVERSAL_TRANSFER_DISABLED", True),
        require_ip_restriction=env_bool("MICRO_LIVE_REQUIRE_IP_RESTRICTION", True),
    )


def audit_live_api_permissions(
    *,
    config: LiveAPIPermissionAuditConfig | None = None,
) -> LiveAPIPermissionAuditReport:
    resolved = config or load_live_api_permission_audit_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved.require_futures_trading_permission and not resolved.futures_trading_permission:
        blockers.append("futures_trading_permission_required")

    if resolved.require_withdrawals_disabled and resolved.withdrawals_permission:
        blockers.append("withdrawals_permission_must_be_disabled")

    if resolved.require_universal_transfer_disabled and resolved.universal_transfer_permission:
        blockers.append("universal_transfer_permission_must_be_disabled")

    if resolved.require_ip_restriction and not resolved.ip_restricted:
        blockers.append("api_key_must_be_ip_restricted")

    if resolved.read_only:
        blockers.append("api_key_read_only_cannot_execute_micro_live")

    if not resolved.ip_restricted:
        warnings.append("api_key_not_ip_restricted")

    recommendations.append("Permissões mínimas: futures trading habilitado, saque/transferência desabilitados.")
    recommendations.append("Usar IP restriction antes de qualquer micro-live.")
    recommendations.append("Nunca habilitar withdrawal em chave de trade.")

    passed = not blockers

    return LiveAPIPermissionAuditReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        futures_trading_permission=resolved.futures_trading_permission,
        withdrawals_permission=resolved.withdrawals_permission,
        universal_transfer_permission=resolved.universal_transfer_permission,
        ip_restricted=resolved.ip_restricted,
        read_only=resolved.read_only,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        config=resolved.model_dump(mode="json"),
    )


def export_live_api_permission_audit_report(
    report: LiveAPIPermissionAuditReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "micro_live_api_permission_audit",
) -> Path:
    resolved = load_live_api_permission_audit_config()
    return export_json(report, output_dir=output_dir or resolved.output_dir, name=name)