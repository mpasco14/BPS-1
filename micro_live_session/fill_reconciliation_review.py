from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live_session.session_models import (
    MicroLiveSessionConfig,
    export_micro_live_session_json,
    load_micro_live_session_config,
)
from micro_live_session.small_order_gate import MicroLiveSmallOrderReport


FillReconStatus = Literal["PASS", "WARN", "FAIL"]


class MicroLiveFillReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_live_fill_reconciliation_review"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: FillReconStatus
    passed: bool

    submitted: bool = False
    filled: bool = False
    canceled: bool = False
    rejected: bool = False
    final_flat: bool = True

    local_position_qty: float = 0.0
    exchange_position_qty: float = 0.0
    position_delta: float = 0.0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    small_order: dict[str, Any]
    config: dict[str, Any]


def review_micro_live_fill_reconciliation(
    *,
    small_order: MicroLiveSmallOrderReport | dict[str, Any],
    submitted: bool = False,
    filled: bool = False,
    canceled: bool = False,
    rejected: bool = False,
    local_position_qty: float = 0.0,
    exchange_position_qty: float = 0.0,
    config: MicroLiveSessionConfig | None = None,
) -> MicroLiveFillReconciliationReport:
    resolved = config or load_micro_live_session_config()
    order = (
        small_order
        if isinstance(small_order, MicroLiveSmallOrderReport)
        else MicroLiveSmallOrderReport.model_validate(small_order)
    )

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    delta = abs(local_position_qty - exchange_position_qty)
    final_flat = abs(local_position_qty) <= 1e-12 and abs(exchange_position_qty) <= 1e-12

    if not order.passed:
        blockers.append("small_order_gate_not_passed")

    if rejected and resolved.require_no_rejection:
        blockers.append("live_order_rejection_detected")

    if submitted and not filled and not canceled:
        warnings.append("submitted_order_without_fill_or_cancel")

    if delta > 1e-12:
        blockers.append("local_exchange_position_mismatch")

    if resolved.require_final_flat and not final_flat:
        blockers.append("final_position_not_flat")

    if not submitted and order.dry_run:
        warnings.append("fill_reconciliation_is_dry_run_only")

    recommendations.append("Depois de ordem real, reconciliar exchange vs ledger local antes de encerrar.")
    recommendations.append("Se houver rejeição ou divergência, bloquear próxima sessão.")

    passed = not blockers

    return MicroLiveFillReconciliationReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        submitted=submitted,
        filled=filled,
        canceled=canceled,
        rejected=rejected,
        final_flat=final_flat,
        local_position_qty=local_position_qty,
        exchange_position_qty=exchange_position_qty,
        position_delta=round(delta, 12),
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        small_order=order.model_dump(mode="json"),
        config=resolved.model_dump(mode="json"),
    )


def export_micro_live_fill_reconciliation_report(
    report: MicroLiveFillReconciliationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "micro_live_fill_reconciliation_review",
) -> Path:
    return export_micro_live_session_json(report, output_dir=output_dir, name=name)