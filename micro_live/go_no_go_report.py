from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live.api_permission_audit import LiveAPIPermissionAuditReport, audit_live_api_permissions
from micro_live.common import export_json
from micro_live.credential_isolation import LiveCredentialIsolationReport, evaluate_live_credential_isolation
from micro_live.emergency_shutdown_drill import EmergencyShutdownDrillReport, run_emergency_shutdown_drill
from micro_live.human_approval import HumanApprovalReport, evaluate_human_approval
from micro_live.risk_envelope import MicroCapitalRiskEnvelopeReport, evaluate_micro_capital_risk_envelope


GoNoGoStatus = Literal["GO", "NO_GO", "WARN"]
GoNoGoDecision = Literal["APPROVED_FOR_MICRO_LIVE_SESSION", "BLOCKED", "REPEAT_PREP_GATE"]


class MicroLiveGoNoGoReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_live_go_no_go_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: GoNoGoStatus
    passed: bool
    decision: GoNoGoDecision

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    credential_isolation: dict[str, Any]
    permission_audit: dict[str, Any]
    risk_envelope: dict[str, Any]
    human_approval: dict[str, Any]
    emergency_shutdown_drill: dict[str, Any]


def build_micro_live_go_no_go_report(
    *,
    credential_isolation: LiveCredentialIsolationReport | dict[str, Any],
    permission_audit: LiveAPIPermissionAuditReport | dict[str, Any],
    risk_envelope: MicroCapitalRiskEnvelopeReport | dict[str, Any],
    human_approval: HumanApprovalReport | dict[str, Any],
    emergency_shutdown_drill: EmergencyShutdownDrillReport | dict[str, Any],
) -> MicroLiveGoNoGoReport:
    credentials = (
        credential_isolation
        if isinstance(credential_isolation, LiveCredentialIsolationReport)
        else LiveCredentialIsolationReport.model_validate(credential_isolation)
    )
    permissions = (
        permission_audit
        if isinstance(permission_audit, LiveAPIPermissionAuditReport)
        else LiveAPIPermissionAuditReport.model_validate(permission_audit)
    )
    risk = (
        risk_envelope
        if isinstance(risk_envelope, MicroCapitalRiskEnvelopeReport)
        else MicroCapitalRiskEnvelopeReport.model_validate(risk_envelope)
    )
    approval = (
        human_approval
        if isinstance(human_approval, HumanApprovalReport)
        else HumanApprovalReport.model_validate(human_approval)
    )
    emergency = (
        emergency_shutdown_drill
        if isinstance(emergency_shutdown_drill, EmergencyShutdownDrillReport)
        else EmergencyShutdownDrillReport.model_validate(emergency_shutdown_drill)
    )

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    components = {
        "credential_isolation": credentials,
        "permission_audit": permissions,
        "risk_envelope": risk,
        "human_approval": approval,
        "emergency_shutdown_drill": emergency,
    }

    for name, report in components.items():
        if not report.passed:
            blockers.append(f"{name}_not_passed")
            blockers.extend([f"{name}:{item}" for item in report.blockers])

        warnings.extend([f"{name}:{item}" for item in report.warnings])
        recommendations.extend(report.recommendations)

    if blockers:
        status: GoNoGoStatus = "NO_GO"
        decision: GoNoGoDecision = "BLOCKED"
    elif warnings:
        status = "WARN"
        decision = "REPEAT_PREP_GATE"
    else:
        status = "GO"
        decision = "APPROVED_FOR_MICRO_LIVE_SESSION"

    if decision == "APPROVED_FOR_MICRO_LIVE_SESSION":
        recommendations.append("Aprovação permite apenas UMA sessão micro-live supervisionada com envelope definido.")
        recommendations.append("Não aumentar capital sem nova fase de validação.")

    passed = not blockers

    return MicroLiveGoNoGoReport(
        status=status,
        passed=passed,
        decision=decision,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        credential_isolation=credentials.model_dump(mode="json"),
        permission_audit=permissions.model_dump(mode="json"),
        risk_envelope=risk.model_dump(mode="json"),
        human_approval=approval.model_dump(mode="json"),
        emergency_shutdown_drill=emergency.model_dump(mode="json"),
    )


def run_micro_live_preparation_gate() -> MicroLiveGoNoGoReport:
    credentials = evaluate_live_credential_isolation()
    permissions = audit_live_api_permissions()
    risk = evaluate_micro_capital_risk_envelope()
    approval = evaluate_human_approval()
    emergency = run_emergency_shutdown_drill()

    return build_micro_live_go_no_go_report(
        credential_isolation=credentials,
        permission_audit=permissions,
        risk_envelope=risk,
        human_approval=approval,
        emergency_shutdown_drill=emergency,
    )


def export_micro_live_go_no_go_report(
    report: MicroLiveGoNoGoReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "micro_live_go_no_go_report",
) -> Path:
    path = Path(output_dir or os.getenv("MICRO_LIVE_GO_NO_GO_OUTPUT_DIR", "artifacts/micro_live"))
    return export_json(report, output_dir=path, name=name)