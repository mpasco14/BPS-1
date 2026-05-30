from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live_session.dry_run_signal import MicroLiveDryRunSignalReport
from micro_live_session.read_only_check import FirstMicroLiveReadOnlyCheckReport
from micro_live_session.session_models import (
    MicroLiveSessionConfig,
    export_micro_live_session_json,
    load_micro_live_session_config,
)


SmallOrderStatus = Literal["DRY_RUN", "APPROVED", "BLOCKED", "FAIL"]


class MicroLiveSmallOrderReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "first_micro_live_small_order_gate"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: SmallOrderStatus
    passed: bool
    submitted: bool
    dry_run: bool

    symbol: str
    side: str
    quantity: float
    price: float
    notional_usd: float

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    order_plan: dict[str, Any]
    read_only_check: dict[str, Any] | None = None
    dry_run_signal: dict[str, Any] | None = None
    config: dict[str, Any]


def build_micro_live_small_order_gate(
    *,
    read_only_check: FirstMicroLiveReadOnlyCheckReport | dict[str, Any],
    dry_run_signal: MicroLiveDryRunSignalReport | dict[str, Any],
    config: MicroLiveSessionConfig | None = None,
) -> MicroLiveSmallOrderReport:
    resolved = config or load_micro_live_session_config()
    read_only = (
        read_only_check
        if isinstance(read_only_check, FirstMicroLiveReadOnlyCheckReport)
        else FirstMicroLiveReadOnlyCheckReport.model_validate(read_only_check)
    )
    signal = (
        dry_run_signal
        if isinstance(dry_run_signal, MicroLiveDryRunSignalReport)
        else MicroLiveDryRunSignalReport.model_validate(dry_run_signal)
    )

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    notional = resolved.quantity * resolved.price

    if resolved.require_read_only_pass and not read_only.passed:
        blockers.append("read_only_check_not_passed")

    if not signal.passed:
        blockers.append("dry_run_signal_not_passed")
        blockers.extend([f"signal:{item}" for item in signal.blockers])

    if not signal.signal_created:
        blockers.append("dry_run_signal_not_created")

    if resolved.quantity <= 0:
        blockers.append("quantity_must_be_positive")

    if resolved.price <= 0:
        blockers.append("price_must_be_positive")

    if notional > resolved.max_notional_usd:
        blockers.append("order_notional_above_micro_live_limit")

    if resolved.max_leverage > 3:
        blockers.append("leverage_above_micro_live_limit")

    order_plan = {
        "symbol": resolved.symbol,
        "side": resolved.side,
        "quantity": resolved.quantity,
        "price": resolved.price,
        "notional_usd": round(notional, 8),
        "dry_run": resolved.dry_run,
        "allow_live_order": resolved.allow_live_order,
        "max_notional_usd": resolved.max_notional_usd,
    }

    if blockers:
        status: SmallOrderStatus = "BLOCKED"
        submitted = False
        passed = False
    elif resolved.dry_run:
        status = "DRY_RUN"
        submitted = False
        passed = True
        warnings.append("small_order_not_submitted_dry_run")
    elif not resolved.allow_live_order:
        status = "BLOCKED"
        submitted = False
        passed = False
        blockers.append("live_order_not_allowed")
    else:
        status = "APPROVED"
        submitted = False
        passed = True
        warnings.append("order_approved_but_not_submitted_by_this_gate")

    recommendations.append("Este gate não deve enviar ordem diretamente; ele aprova ou bloqueia o plano.")
    recommendations.append("Execução real deve ocorrer em adapter separado, com confirmação humana e logs.")

    return MicroLiveSmallOrderReport(
        status=status,
        passed=passed,
        submitted=submitted,
        dry_run=resolved.dry_run,
        symbol=resolved.symbol,
        side=resolved.side,
        quantity=resolved.quantity,
        price=resolved.price,
        notional_usd=round(notional, 8),
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        order_plan=order_plan,
        read_only_check=read_only.model_dump(mode="json"),
        dry_run_signal=signal.model_dump(mode="json"),
        config=resolved.model_dump(mode="json"),
    )


def export_micro_live_small_order_report(
    report: MicroLiveSmallOrderReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "first_micro_live_small_order_gate",
) -> Path:
    return export_micro_live_session_json(report, output_dir=output_dir, name=name)