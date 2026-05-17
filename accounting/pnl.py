"""
PnL accounting utilities.

Responsabilidades:
- Calcular PnL bruto e líquido.
- Calcular retorno sobre margem e notional.
- Calcular métricas agregadas: win rate, profit factor, drawdown.
- Servir de base para paper trading, backtest e dataset de IA.

Este módulo NÃO executa ordens.
Este módulo NÃO acessa API da Binance.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PositionSide = Literal["LONG", "SHORT"]


class TradePnl(BaseModel):
    model_config = ConfigDict(extra="allow")

    side: PositionSide

    entry_price: float
    exit_price: float
    quantity: float

    margin_usd: float | None = None
    notional_usd: float | None = None

    gross_pnl_usd: float
    fees_usd: float = 0.0
    funding_pnl_usd: float = 0.0
    slippage_usd: float = 0.0
    net_pnl_usd: float

    return_on_margin_pct: float | None = None
    return_on_notional_pct: float | None = None

    is_win: bool

    @field_validator("entry_price", "exit_price", "quantity")
    @classmethod
    def positive_values(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("valor precisa ser maior que zero")
        return float(value)


class PnlSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    trade_count: int
    wins: int
    losses: int

    gross_pnl_usd: float
    net_pnl_usd: float
    total_fees_usd: float
    total_funding_pnl_usd: float
    total_slippage_usd: float

    win_rate: float
    average_win_usd: float
    average_loss_usd: float
    profit_factor: float | None

    max_drawdown_usd: float
    max_drawdown_pct: float

    sharpe_ratio: float | None = None

    trades: list[dict[str, Any]] = Field(default_factory=list)


def calculate_gross_pnl(
    *,
    side: PositionSide,
    entry_price: float,
    exit_price: float,
    quantity: float,
) -> float:
    if side == "LONG":
        return (exit_price - entry_price) * quantity

    return (entry_price - exit_price) * quantity


def calculate_trade_pnl(
    *,
    side: PositionSide,
    entry_price: float,
    exit_price: float,
    quantity: float,
    margin_usd: float | None = None,
    notional_usd: float | None = None,
    fees_usd: float = 0.0,
    funding_pnl_usd: float = 0.0,
    slippage_usd: float = 0.0,
) -> TradePnl:
    gross = calculate_gross_pnl(
        side=side,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
    )

    net = gross + funding_pnl_usd - fees_usd - slippage_usd

    return_on_margin = None
    if margin_usd and margin_usd > 0:
        return_on_margin = net / margin_usd

    return_on_notional = None
    if notional_usd and notional_usd > 0:
        return_on_notional = net / notional_usd

    return TradePnl(
        side=side,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        margin_usd=margin_usd,
        notional_usd=notional_usd,
        gross_pnl_usd=gross,
        fees_usd=fees_usd,
        funding_pnl_usd=funding_pnl_usd,
        slippage_usd=slippage_usd,
        net_pnl_usd=net,
        return_on_margin_pct=return_on_margin,
        return_on_notional_pct=return_on_notional,
        is_win=net > 0,
    )


def build_equity_curve(
    *,
    initial_balance_usd: float,
    pnl_values: list[float],
) -> list[float]:
    equity = [initial_balance_usd]

    running = initial_balance_usd
    for pnl in pnl_values:
        running += pnl
        equity.append(running)

    return equity


def calculate_max_drawdown(equity_curve: list[float]) -> tuple[float, float]:
    if not equity_curve:
        return 0.0, 0.0

    peak = equity_curve[0]
    max_drawdown_usd = 0.0
    max_drawdown_pct = 0.0

    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = peak - equity

        if drawdown > max_drawdown_usd:
            max_drawdown_usd = drawdown
            max_drawdown_pct = drawdown / peak if peak > 0 else 0.0

    return max_drawdown_usd, max_drawdown_pct


def calculate_profit_factor(trades: list[TradePnl]) -> float | None:
    gross_wins = sum(trade.net_pnl_usd for trade in trades if trade.net_pnl_usd > 0)
    gross_losses = abs(sum(trade.net_pnl_usd for trade in trades if trade.net_pnl_usd < 0))

    if gross_losses == 0:
        return None

    return gross_wins / gross_losses


def calculate_sharpe_ratio(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None

    mean_return = statistics.mean(returns)
    std_return = statistics.pstdev(returns)

    if std_return == 0:
        return None

    return mean_return / std_return * math.sqrt(len(returns))


def summarize_pnl(
    trades: list[TradePnl],
    *,
    initial_balance_usd: float = 1000.0,
) -> PnlSummary:
    trade_count = len(trades)
    wins = [trade for trade in trades if trade.net_pnl_usd > 0]
    losses = [trade for trade in trades if trade.net_pnl_usd < 0]

    net_values = [trade.net_pnl_usd for trade in trades]
    equity = build_equity_curve(
        initial_balance_usd=initial_balance_usd,
        pnl_values=net_values,
    )

    max_drawdown_usd, max_drawdown_pct = calculate_max_drawdown(equity)

    returns = [
        trade.return_on_margin_pct
        for trade in trades
        if trade.return_on_margin_pct is not None
    ]

    return PnlSummary(
        trade_count=trade_count,
        wins=len(wins),
        losses=len(losses),
        gross_pnl_usd=sum(trade.gross_pnl_usd for trade in trades),
        net_pnl_usd=sum(trade.net_pnl_usd for trade in trades),
        total_fees_usd=sum(trade.fees_usd for trade in trades),
        total_funding_pnl_usd=sum(trade.funding_pnl_usd for trade in trades),
        total_slippage_usd=sum(trade.slippage_usd for trade in trades),
        win_rate=len(wins) / trade_count if trade_count > 0 else 0.0,
        average_win_usd=sum(trade.net_pnl_usd for trade in wins) / len(wins) if wins else 0.0,
        average_loss_usd=sum(trade.net_pnl_usd for trade in losses) / len(losses) if losses else 0.0,
        profit_factor=calculate_profit_factor(trades),
        max_drawdown_usd=max_drawdown_usd,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=calculate_sharpe_ratio(returns),
        trades=[trade.model_dump(mode="json") for trade in trades],
    )


def pnl_to_dict(pnl: TradePnl) -> dict[str, Any]:
    return pnl.model_dump(mode="json")


def summary_to_dict(summary: PnlSummary) -> dict[str, Any]:
    return summary.model_dump(mode="json")