from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


class LiveGuardConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True

    allowed_symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT"])
    required_margin_type: str = "ISOLATED"

    max_leverage: int = 30
    max_margin_usd: float = 20.0
    max_notional_usd: float = 600.0
    max_order_qty: float = 0.010

    require_live_flags: bool = True
    require_safety_gate_approved: bool = True
    require_capital_ramp_approved: bool = True
    require_reduce_only_for_emergency: bool = False


class LiveOrderContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    side: str
    quantity: float
    price: float | None = None
    notional_usd: float
    margin_usd: float
    leverage: int

    margin_type: str = "ISOLATED"
    reduce_only: bool = False

    binance_allow_live_trading: bool = False
    risk_allow_live_trading: bool = False
    binance_execution_mode: str = "paper"

    safety_gate_approved: bool = False
    capital_ramp_approved: bool = False
    emergency_mode: bool = False


class LiveGuardDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    approved: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_live_guard_config() -> LiveGuardConfig:
    allowed_symbols = [
        item.strip().upper()
        for item in os.getenv("LIVE_GUARD_ALLOWED_SYMBOLS", "BTCUSDT").split(",")
        if item.strip()
    ]

    return LiveGuardConfig(
        enabled=env_bool("LIVE_GUARD_ENABLED", True),
        allowed_symbols=allowed_symbols,
        required_margin_type=os.getenv("LIVE_GUARD_REQUIRED_MARGIN_TYPE", "ISOLATED").strip().upper(),
        max_leverage=env_int("LIVE_GUARD_MAX_LEVERAGE", 30),
        max_margin_usd=env_float("LIVE_GUARD_MAX_MARGIN_USD", 20),
        max_notional_usd=env_float("LIVE_GUARD_MAX_NOTIONAL_USD", 600),
        max_order_qty=env_float("LIVE_GUARD_MAX_ORDER_QTY", 0.010),
        require_live_flags=env_bool("LIVE_GUARD_REQUIRE_LIVE_FLAGS", True),
        require_safety_gate_approved=env_bool("LIVE_GUARD_REQUIRE_SAFETY_GATE_APPROVED", True),
        require_capital_ramp_approved=env_bool("LIVE_GUARD_REQUIRE_CAPITAL_RAMP_APPROVED", True),
        require_reduce_only_for_emergency=env_bool("LIVE_GUARD_REQUIRE_REDUCE_ONLY_FOR_EMERGENCY", False),
    )


def evaluate_live_order_guard(
    *,
    context: LiveOrderContext | dict[str, Any],
    config: LiveGuardConfig | None = None,
) -> LiveGuardDecision:
    resolved_context = context if isinstance(context, LiveOrderContext) else LiveOrderContext.model_validate(context)
    resolved_config = config or load_live_guard_config()

    blockers: list[str] = []
    warnings: list[str] = []

    if not resolved_config.enabled:
        blockers.append("live_guard_disabled")

    if resolved_context.symbol.upper() not in resolved_config.allowed_symbols:
        blockers.append("symbol_not_allowed")

    if resolved_context.margin_type.upper() != resolved_config.required_margin_type:
        blockers.append("invalid_margin_type")

    if resolved_context.leverage > resolved_config.max_leverage:
        blockers.append("leverage_above_limit")

    if resolved_context.margin_usd > resolved_config.max_margin_usd:
        blockers.append("margin_above_limit")

    if resolved_context.notional_usd > resolved_config.max_notional_usd:
        blockers.append("notional_above_limit")

    if resolved_context.quantity > resolved_config.max_order_qty:
        blockers.append("quantity_above_limit")

    if resolved_config.require_live_flags:
        if not resolved_context.binance_allow_live_trading:
            blockers.append("binance_live_flag_not_enabled")

        if not resolved_context.risk_allow_live_trading:
            blockers.append("risk_live_flag_not_enabled")

        if resolved_context.binance_execution_mode.lower() != "live":
            blockers.append("execution_mode_not_live")

    if resolved_config.require_safety_gate_approved and not resolved_context.safety_gate_approved:
        blockers.append("safety_gate_not_approved")

    if resolved_config.require_capital_ramp_approved and not resolved_context.capital_ramp_approved:
        blockers.append("capital_ramp_not_approved")

    if (
        resolved_context.emergency_mode
        and resolved_config.require_reduce_only_for_emergency
        and not resolved_context.reduce_only
    ):
        blockers.append("emergency_order_must_be_reduce_only")

    if resolved_context.price is None:
        warnings.append("price_missing_for_market_order")

    return LiveGuardDecision(
        approved=len(blockers) == 0,
        blockers=blockers,
        warnings=warnings,
        context=resolved_context.model_dump(mode="json"),
    )