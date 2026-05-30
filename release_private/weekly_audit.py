from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from release_private.release_models import ComponentReport, PrivateReleaseConfig, export_release_json, load_private_release_config


class WeeklyAuditInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    operator_name: str = ""
    reviewed_trades: bool = False
    reviewed_rejections: bool = False
    reviewed_risk_limits: bool = False
    reviewed_artifacts: bool = False
    reviewed_config_changes: bool = False
    reviewed_security: bool = False
    reviewed_model_drift: bool = False
    reviewed_runbooks: bool = False


def build_weekly_audit_routine(
    *,
    inputs: WeeklyAuditInputs | dict[str, Any] | None = None,
    config: PrivateReleaseConfig | None = None,
) -> ComponentReport:
    resolved = config or load_private_release_config()
    parsed = (
        inputs
        if isinstance(inputs, WeeklyAuditInputs)
        else WeeklyAuditInputs.model_validate(inputs)
        if inputs is not None
        else WeeklyAuditInputs(
            operator_name=resolved.operator_name,
            reviewed_trades=resolved.weekly_audit_confirmed,
            reviewed_rejections=resolved.weekly_audit_confirmed,
            reviewed_risk_limits=resolved.weekly_audit_confirmed,
            reviewed_artifacts=resolved.weekly_audit_confirmed,
            reviewed_config_changes=resolved.weekly_audit_confirmed,
            reviewed_security=resolved.weekly_audit_confirmed,
            reviewed_model_drift=resolved.weekly_audit_confirmed,
            reviewed_runbooks=resolved.weekly_audit_confirmed,
        )
    )

    blockers: list[str] = []
    recommendations: list[str] = []

    checks = parsed.model_dump(mode="json")
    checks.pop("operator_name", None)

    if not parsed.operator_name:
        blockers.append("operator_name_required")

    for name, value in checks.items():
        if value is not True:
            blockers.append(f"weekly_audit_not_confirmed:{name}")

    recommendations.append("Auditoria semanal deve revisar risco, segurança, drift, artifacts e runbooks.")
    recommendations.append("Aumentos de capital exigem nova aprovação e novo relatório.")

    passed = not blockers

    return ComponentReport(
        source="private_release_weekly_audit_routine",
        status="PASS" if passed else "FAIL",
        passed=passed,
        blockers=sorted(set(blockers)),
        warnings=[],
        recommendations=sorted(set(recommendations)),
        metadata=parsed.model_dump(mode="json"),
    )


def export_weekly_audit_routine_report(
    report: ComponentReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "private_release_weekly_audit_routine",
) -> Path:
    return export_release_json(report, output_dir=output_dir, name=name)