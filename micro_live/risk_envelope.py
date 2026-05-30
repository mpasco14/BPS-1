from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live.common import env_bool, env_float, env_int, export_json


RiskEnvelopeStatus = Literal["PASS", "WARN", "FAIL"]


class MicroCapitalRiskEnvelopeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/micro_live")

    max_capital_usd: float = 25.0
    max_order_notional_usd: float = 10.0
    max_daily_loss_usd: float = 3.0
    max_leverage: int = 3
    max_orders_per_session: int = 1

    require_flat_start: bool = True
    require_flat_end: bool = True


class MicroCapitalRiskEnvelopeReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_capital_risk_envelope"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: RiskEnvelopeStatus
    passed: bool

    max_capital_usd: float
    max_order_notional_usd: float
    max_daily_loss_usd: float
    max_leverage: int
    max_orders_per_session: int

    risk_per_session_pct: float
    notional_to_capital_pct: float

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    config: dict[str, Any]


def load_micro_capital_risk_envelope_config() -> MicroCapitalRiskEnvelopeConfig:
    return MicroCapitalRiskEnvelopeConfig(
        output_dir=Path(os.getenv("MICRO_LIVE_OUTPUT_DIR", "artifacts/micro_live")),
        max_capital_usd=env_float("MICRO_LIVE_MAX_CAPITAL_USD", 25),
        max_order_notional_usd=env_float("MICRO_LIVE_MAX_ORDER_NOTIONAL_USD", 10),
        max_daily_loss_usd=env_float("MICRO_LIVE_MAX_DAILY_LOSS_USD", 3),
        max_leverage=env_int("MICRO_LIVE_MAX_LEVERAGE", 3),
        max_orders_per_session=env_int("MICRO_LIVE_MAX_ORDERS_PER_SESSION", 1),
        require_flat_start=env_bool("MICRO_LIVE_REQUIRE_FLAT_START", True),
        require_flat_end=env_bool("MICRO_LIVE_REQUIRE_FLAT_END", True),
    )


def evaluate_micro_capital_risk_envelope(
    *,
    config: MicroCapitalRiskEnvelopeConfig | None = None,
) -> MicroCapitalRiskEnvelopeReport:
    resolved = config or load_micro_capital_risk_envelope_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved.max_capital_usd <= 0:
        blockers.append("max_capital_must_be_positive")

    if resolved.max_order_notional_usd <= 0:
        blockers.append("max_order_notional_must_be_positive")

    if resolved.max_daily_loss_usd <= 0:
        blockers.append("max_daily_loss_must_be_positive")

    if resolved.max_leverage <= 0:
        blockers.append("max_leverage_must_be_positive")

    if resolved.max_orders_per_session <= 0:
        blockers.append("max_orders_per_session_must_be_positive")

    if resolved.max_order_notional_usd > resolved.max_capital_usd:
        blockers.append("order_notional_cannot_exceed_micro_capital")

    if resolved.max_daily_loss_usd > resolved.max_capital_usd * 0.25:
        blockers.append("daily_loss_limit_too_high_for_micro_live")

    if resolved.max_leverage > 3:
        blockers.append("micro_live_leverage_above_limit")

    if resolved.max_orders_per_session > 3:
        blockers.append("too_many_orders_for_first_micro_live")

    risk_per_session_pct = (
        resolved.max_daily_loss_usd / resolved.max_capital_usd
        if resolved.max_capital_usd > 0
        else 0.0
    )
    notional_to_capital_pct = (
        resolved.max_order_notional_usd / resolved.max_capital_usd
        if resolved.max_capital_usd > 0
        else 0.0
    )

    if risk_per_session_pct > 0.10:
        warnings.append("daily_loss_above_10pct_of_micro_capital")

    recommendations.append("Primeiro micro-live deve usar capital mínimo e apenas 1 ordem.")
    recommendations.append("Encerrar sessão flat e reconciliada.")
    recommendations.append("Não aumentar capital automaticamente após uma sessão positiva.")

    passed = not blockers

    return MicroCapitalRiskEnvelopeReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        max_capital_usd=resolved.max_capital_usd,
        max_order_notional_usd=resolved.max_order_notional_usd,
        max_daily_loss_usd=resolved.max_daily_loss_usd,
        max_leverage=resolved.max_leverage,
        max_orders_per_session=resolved.max_orders_per_session,
        risk_per_session_pct=round(risk_per_session_pct, 6),
        notional_to_capital_pct=round(notional_to_capital_pct, 6),
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        config=resolved.model_dump(mode="json"),
    )


def export_micro_capital_risk_envelope_report(
    report: MicroCapitalRiskEnvelopeReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "micro_capital_risk_envelope",
) -> Path:
    resolved = load_micro_capital_risk_envelope_config()
    return export_json(report, output_dir=output_dir or resolved.output_dir, name=name)