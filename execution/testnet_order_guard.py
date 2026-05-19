"""
Testnet order guard.

Responsabilidades:
- Bloquear envio de ordem testnet quando credenciais ou flags não estiverem corretas.
- Validar símbolo, notional e quantidade.
- Não envia ordens.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from execution.binance_testnet_client import BinanceTestnetConfig, evaluate_binance_testnet_readiness


load_dotenv()


class TestnetOrderGuardConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True

    require_testnet_ready: bool = True
    require_submission_flag: bool = True

    allowed_symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT"])

    max_notional_usd: float = 600.0
    max_qty: float = 0.010


class TestnetOrderContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    side: str
    quantity: float
    notional_usd: float

    order_type: str = "LIMIT"
    price: float | None = None

    testnet_ready: bool = False
    testnet_allow_order_submission: bool = False


class TestnetOrderGuardDecision(BaseModel):
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


def load_testnet_order_guard_config() -> TestnetOrderGuardConfig:
    symbols = [
        item.strip().upper()
        for item in os.getenv("TESTNET_ORDER_GUARD_ALLOWED_SYMBOLS", "BTCUSDT").split(",")
        if item.strip()
    ]

    return TestnetOrderGuardConfig(
        enabled=env_bool("TESTNET_ORDER_GUARD_ENABLED", True),
        require_testnet_ready=env_bool("TESTNET_ORDER_GUARD_REQUIRE_TESTNET_READY", True),
        require_submission_flag=env_bool("TESTNET_ORDER_GUARD_REQUIRE_SUBMISSION_FLAG", True),
        allowed_symbols=symbols,
        max_notional_usd=env_float("TESTNET_ORDER_GUARD_MAX_NOTIONAL_USD", 600),
        max_qty=env_float("TESTNET_ORDER_GUARD_MAX_QTY", 0.010),
    )


def build_context_from_testnet_config(
    *,
    symbol: str,
    side: str,
    quantity: float,
    notional_usd: float,
    order_type: str = "LIMIT",
    price: float | None = None,
    testnet_config: BinanceTestnetConfig | None = None,
) -> TestnetOrderContext:
    readiness = evaluate_binance_testnet_readiness(testnet_config)

    return TestnetOrderContext(
        symbol=symbol,
        side=side,
        quantity=quantity,
        notional_usd=notional_usd,
        order_type=order_type,
        price=price,
        testnet_ready=readiness.ready,
        testnet_allow_order_submission=readiness.allow_order_submission,
    )


def evaluate_testnet_order_guard(
    *,
    context: TestnetOrderContext | dict[str, Any],
    config: TestnetOrderGuardConfig | None = None,
) -> TestnetOrderGuardDecision:
    resolved_context = context if isinstance(context, TestnetOrderContext) else TestnetOrderContext.model_validate(context)
    resolved_config = config or load_testnet_order_guard_config()

    blockers: list[str] = []
    warnings: list[str] = []

    if not resolved_config.enabled:
        blockers.append("testnet_order_guard_disabled")

    if resolved_context.symbol.upper() not in resolved_config.allowed_symbols:
        blockers.append("symbol_not_allowed")

    if resolved_context.notional_usd > resolved_config.max_notional_usd:
        blockers.append("notional_above_limit")

    if resolved_context.quantity > resolved_config.max_qty:
        blockers.append("quantity_above_limit")

    if resolved_config.require_testnet_ready and not resolved_context.testnet_ready:
        blockers.append("testnet_not_ready")

    if resolved_config.require_submission_flag and not resolved_context.testnet_allow_order_submission:
        blockers.append("testnet_order_submission_not_allowed")

    if resolved_context.order_type.upper() == "MARKET":
        warnings.append("market_order_on_testnet")

    return TestnetOrderGuardDecision(
        approved=len(blockers) == 0,
        blockers=blockers,
        warnings=warnings,
        context=resolved_context.model_dump(mode="json"),
    )