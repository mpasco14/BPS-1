from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live.go_no_go_report import MicroLiveGoNoGoReport, run_micro_live_preparation_gate
from micro_live_session.session_models import (
    MicroLiveSessionConfig,
    export_micro_live_session_json,
    load_micro_live_session_config,
)


ReadOnlyStatus = Literal["PASS", "WARN", "FAIL"]


class FirstMicroLiveReadOnlyCheckReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "first_micro_live_read_only_check"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ReadOnlyStatus
    passed: bool

    prep_gate_passed: bool
    prep_gate_decision: str
    live_order_allowed: bool
    dry_run: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    go_no_go_report: dict[str, Any]


def build_first_micro_live_read_only_check(
    *,
    go_no_go_report: MicroLiveGoNoGoReport | dict[str, Any] | None = None,
    config: MicroLiveSessionConfig | None = None,
) -> FirstMicroLiveReadOnlyCheckReport:
    resolved = config or load_micro_live_session_config()

    gate = (
        go_no_go_report
        if isinstance(go_no_go_report, MicroLiveGoNoGoReport)
        else MicroLiveGoNoGoReport.model_validate(go_no_go_report)
        if go_no_go_report is not None
        else run_micro_live_preparation_gate()
    )

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved.require_prep_gate and not gate.passed:
        blockers.append("micro_live_preparation_gate_not_passed")
        blockers.extend([f"prep_gate:{item}" for item in gate.blockers])

    if resolved.require_human_approval:
        approval = gate.human_approval or {}
        if not approval.get("passed", False):
            blockers.append("human_approval_not_passed")

    if resolved.allow_live_order and resolved.dry_run:
        warnings.append("live_order_allowed_but_session_is_dry_run")

    if resolved.allow_live_order and gate.decision != "APPROVED_FOR_MICRO_LIVE_SESSION":
        blockers.append("live_order_requires_go_decision")

    recommendations.append("Read-only check aprovado não envia ordem.")
    recommendations.append("Ordem micro-live exige dry_run=false e allow_live_order=true explicitamente.")

    passed = not blockers

    return FirstMicroLiveReadOnlyCheckReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        prep_gate_passed=gate.passed,
        prep_gate_decision=gate.decision,
        live_order_allowed=resolved.allow_live_order,
        dry_run=resolved.dry_run,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        go_no_go_report=gate.model_dump(mode="json"),
    )


def export_first_micro_live_read_only_check_report(
    report: FirstMicroLiveReadOnlyCheckReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "first_micro_live_read_only_check",
) -> Path:
    return export_micro_live_session_json(report, output_dir=output_dir, name=name)