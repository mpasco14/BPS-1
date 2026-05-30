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


DryRunSignalStatus = Literal["PASS", "WARN", "FAIL", "NO_TRADE"]


class MicroLiveDryRunSignalInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    side: Literal["BUY", "SELL"] = "BUY"
    confidence: float = 0.75
    edge_pct: float = 0.002

    no_trade: bool = False
    strategy_health_passed: bool = True
    no_trade_engine_passed: bool = True
    read_only_passed: bool = True

    metadata: dict[str, Any] = Field(default_factory=dict)


class MicroLiveDryRunSignalReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "first_micro_live_dry_run_signal"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: DryRunSignalStatus
    passed: bool
    signal_created: bool

    symbol: str
    side: str
    confidence: float
    edge_pct: float

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    input: dict[str, Any]
    config: dict[str, Any]


def evaluate_micro_live_dry_run_signal(
    *,
    signal_input: MicroLiveDryRunSignalInput | dict[str, Any] | None = None,
    config: MicroLiveSessionConfig | None = None,
) -> MicroLiveDryRunSignalReport:
    resolved = config or load_micro_live_session_config()
    parsed = (
        signal_input
        if isinstance(signal_input, MicroLiveDryRunSignalInput)
        else MicroLiveDryRunSignalInput.model_validate(signal_input)
        if signal_input is not None
        else MicroLiveDryRunSignalInput(symbol=resolved.symbol, side=resolved.side)
    )

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if parsed.no_trade and not resolved.allow_no_trade:
        return MicroLiveDryRunSignalReport(
            status="NO_TRADE",
            passed=True,
            signal_created=False,
            symbol=parsed.symbol,
            side=parsed.side,
            confidence=parsed.confidence,
            edge_pct=parsed.edge_pct,
            blockers=[],
            warnings=["no_trade_signal_respected"],
            recommendations=["Não operar quando No-Trade Engine bloquear."],
            input=parsed.model_dump(mode="json"),
            config=resolved.model_dump(mode="json"),
        )

    if not parsed.read_only_passed:
        blockers.append("read_only_check_not_passed")

    if not parsed.strategy_health_passed:
        blockers.append("strategy_health_not_passed")

    if not parsed.no_trade_engine_passed:
        blockers.append("no_trade_engine_not_passed")

    if parsed.confidence < resolved.min_confidence:
        blockers.append("confidence_below_micro_live_minimum")

    if parsed.edge_pct < resolved.min_edge_pct:
        blockers.append("edge_below_micro_live_minimum")

    recommendations.append("Dry-run signal não autoriza ordem live sozinho.")
    recommendations.append("Exigir order gate e kill switch antes de qualquer envio.")

    passed = not blockers

    return MicroLiveDryRunSignalReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        signal_created=passed,
        symbol=parsed.symbol,
        side=parsed.side,
        confidence=parsed.confidence,
        edge_pct=parsed.edge_pct,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        input=parsed.model_dump(mode="json"),
        config=resolved.model_dump(mode="json"),
    )


def export_micro_live_dry_run_signal_report(
    report: MicroLiveDryRunSignalReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "first_micro_live_dry_run_signal",
) -> Path:
    return export_micro_live_session_json(report, output_dir=output_dir, name=name)