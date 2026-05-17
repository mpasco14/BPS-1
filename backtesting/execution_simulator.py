"""
Backtesting execution simulator.

Responsabilidades:
- Simular execução de uma ordem aprovada pelo risk_manager.
- Aplicar slippage de entrada e saída.
- Aplicar fees.
- Aplicar funding cost/pnl.
- Usar TP/SL/time-barrier labeler.
- Retornar resultado realista para backtest e dataset de IA.

Este módulo NÃO envia ordens reais.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from accounting.pnl import TradePnl, calculate_trade_pnl
from execution.paper_executor import (
    apply_entry_slippage,
    apply_exit_slippage,
    reprice_order_plan,
)
from models.labeler import BarrierLabel, label_price_path
from risk.risk_manager import OrderRiskPlan


load_dotenv()


SimulationOutcome = Literal["take_profit", "stop_loss", "time_barrier", "no_data"]


class ExecutionSimulationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "execution_simulator"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str

    side: Literal["LONG", "SHORT"]

    outcome: SimulationOutcome
    target: int | None

    entry_price_requested: float
    entry_price_filled: float
    exit_price_raw: float
    exit_price_filled: float

    quantity: float
    notional_usd: float
    margin_usd: float
    leverage: float

    take_profit_price: float
    stop_loss_price: float

    label: dict[str, Any]
    pnl: dict[str, Any]

    simulated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def env_float(name: str, default: float) -> float:
    parsed = safe_float(os.getenv(name))

    if parsed is None:
        return default

    return parsed


def parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def simulate_execution(
    *,
    order_plan: OrderRiskPlan,
    price_path: list[dict[str, Any]],
    slippage_pct: float | None = None,
    entry_fee_usd: float | None = None,
    exit_fee_usd: float | None = None,
    funding_cost_usd: float | None = None,
    max_holding_seconds: int | None = None,
    conservative_on_ambiguous: bool | None = None,
) -> ExecutionSimulationResult:
    slippage = (
        slippage_pct
        if slippage_pct is not None
        else env_float("EXECUTION_SIMULATOR_SLIPPAGE_PCT", 0.0005)
    )

    entry_fee = (
        entry_fee_usd
        if entry_fee_usd is not None
        else env_float("EXECUTION_SIMULATOR_ENTRY_FEE_USD", 0.05)
    )

    exit_fee = (
        exit_fee_usd
        if exit_fee_usd is not None
        else env_float("EXECUTION_SIMULATOR_EXIT_FEE_USD", 0.05)
    )

    funding_cost = (
        funding_cost_usd
        if funding_cost_usd is not None
        else env_float("EXECUTION_SIMULATOR_FUNDING_COST_USD", 0.0)
    )

    conservative = (
        conservative_on_ambiguous
        if conservative_on_ambiguous is not None
        else parse_bool(os.getenv("EXECUTION_SIMULATOR_CONSERVATIVE_ON_AMBIGUOUS"), default=True)
    )

    filled_entry_price = apply_entry_slippage(
        direction=order_plan.direction,
        entry_price=order_plan.entry_price,
        slippage_pct=slippage,
    )

    filled_plan = reprice_order_plan(
        order_plan,
        filled_entry_price=filled_entry_price,
    )

    label: BarrierLabel = label_price_path(
        side=filled_plan.direction,
        entry_price=filled_plan.entry_price,
        price_path=price_path,
        take_profit_price=filled_plan.take_profit_price,
        stop_loss_price=filled_plan.stop_loss_price,
        quantity=filled_plan.quantity,
        max_holding_seconds=max_holding_seconds,
        conservative_on_ambiguous=conservative,
        timeframe=filled_plan.timeframe,
    )

    filled_exit_price = apply_exit_slippage(
        side=filled_plan.direction,
        exit_price=label.exit_price,
        slippage_pct=slippage,
    )

    fees = entry_fee + exit_fee

    # funding_cost_usd positivo representa custo pago pelo trade.
    pnl: TradePnl = calculate_trade_pnl(
        side=filled_plan.direction,
        entry_price=filled_plan.entry_price,
        exit_price=filled_exit_price,
        quantity=filled_plan.quantity,
        margin_usd=filled_plan.margin_usd,
        notional_usd=filled_plan.notional_usd,
        fees_usd=fees,
        funding_pnl_usd=-funding_cost,
        slippage_usd=0.0,
    )

    return ExecutionSimulationResult(
        venue=filled_plan.venue,
        symbol=filled_plan.symbol,
        timeframe=filled_plan.timeframe,
        side=filled_plan.direction,
        outcome=label.outcome,
        target=label.target,
        entry_price_requested=order_plan.entry_price,
        entry_price_filled=filled_plan.entry_price,
        exit_price_raw=label.exit_price,
        exit_price_filled=filled_exit_price,
        quantity=filled_plan.quantity,
        notional_usd=filled_plan.notional_usd,
        margin_usd=filled_plan.margin_usd,
        leverage=filled_plan.leverage,
        take_profit_price=filled_plan.take_profit_price,
        stop_loss_price=filled_plan.stop_loss_price,
        label=label.model_dump(mode="json"),
        pnl=pnl.model_dump(mode="json"),
    )


def simulation_to_dict(result: ExecutionSimulationResult) -> dict[str, Any]:
    return result.model_dump(mode="json")