"""
Paper/accounting positions.

Responsabilidades:
- Controlar posições abertas e fechadas.
- Calcular PnL realizado e não realizado.
- Aplicar TP/SL em simulação.
- Servir de base para backtest e paper_executor.

Este módulo NÃO acessa exchange real.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from risk.risk_manager import OrderRiskPlan


PositionSide = Literal["LONG", "SHORT"]
PositionStatus = Literal["OPEN", "CLOSED"]
CloseReason = Literal["take_profit", "stop_loss", "manual", "expired", "risk_exit"]


class Position(BaseModel):
    model_config = ConfigDict(extra="allow")

    position_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str

    side: PositionSide

    quantity: float
    entry_price: float
    notional_usd: float
    margin_usd: float
    leverage: float

    take_profit_price: float
    stop_loss_price: float

    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: PositionStatus = "OPEN"

    exit_price: float | None = None
    closed_at: datetime | None = None
    close_reason: CloseReason | None = None

    entry_fee_usd: float = 0.0
    exit_fee_usd: float = 0.0

    realized_pnl_usd: float = 0.0
    gross_pnl_usd: float = 0.0

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("symbol não pode ser vazio")
        return value

    @field_validator("quantity", "entry_price", "notional_usd", "margin_usd", "leverage")
    @classmethod
    def positive_values(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("valor precisa ser maior que zero")
        return float(value)


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


def calculate_unrealized_pnl(position: Position, mark_price: float) -> float:
    if position.status != "OPEN":
        return 0.0

    return calculate_gross_pnl(
        side=position.side,
        entry_price=position.entry_price,
        exit_price=mark_price,
        quantity=position.quantity,
    )


def check_exit_condition(position: Position, price: float) -> CloseReason | None:
    if position.status != "OPEN":
        return None

    if position.side == "LONG":
        if price >= position.take_profit_price:
            return "take_profit"
        if price <= position.stop_loss_price:
            return "stop_loss"

    if position.side == "SHORT":
        if price <= position.take_profit_price:
            return "take_profit"
        if price >= position.stop_loss_price:
            return "stop_loss"

    return None


def close_position(
    position: Position,
    *,
    exit_price: float,
    reason: CloseReason,
    exit_fee_usd: float = 0.0,
    closed_at: datetime | None = None,
) -> Position:
    gross_pnl = calculate_gross_pnl(
        side=position.side,
        entry_price=position.entry_price,
        exit_price=exit_price,
        quantity=position.quantity,
    )

    realized_pnl = gross_pnl - position.entry_fee_usd - exit_fee_usd

    return position.model_copy(
        update={
            "status": "CLOSED",
            "exit_price": exit_price,
            "closed_at": closed_at or datetime.now(timezone.utc),
            "close_reason": reason,
            "exit_fee_usd": exit_fee_usd,
            "gross_pnl_usd": gross_pnl,
            "realized_pnl_usd": realized_pnl,
        }
    )


def build_position_from_order_plan(
    plan: OrderRiskPlan,
    *,
    entry_fee_usd: float = 0.0,
    position_id: str | None = None,
    opened_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> Position:
    return Position(
        position_id=position_id or str(uuid.uuid4()),
        venue=plan.venue,
        symbol=plan.symbol,
        timeframe=plan.timeframe,
        side=plan.direction,
        quantity=plan.quantity,
        entry_price=plan.entry_price,
        notional_usd=plan.notional_usd,
        margin_usd=plan.margin_usd,
        leverage=plan.leverage,
        take_profit_price=plan.take_profit_price,
        stop_loss_price=plan.stop_loss_price,
        opened_at=opened_at or datetime.now(timezone.utc),
        entry_fee_usd=entry_fee_usd,
        metadata=metadata or {},
    )


class PositionBook:
    def __init__(self) -> None:
        self._open_positions: dict[str, Position] = {}
        self._closed_positions: list[Position] = []

    def open_position(self, position: Position) -> Position:
        if position.status != "OPEN":
            raise ValueError("somente posições OPEN podem ser adicionadas como abertas")

        self._open_positions[position.position_id] = position

        return position

    def open_from_order_plan(
        self,
        plan: OrderRiskPlan,
        *,
        entry_fee_usd: float = 0.0,
        position_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Position:
        position = build_position_from_order_plan(
            plan,
            entry_fee_usd=entry_fee_usd,
            position_id=position_id,
            metadata=metadata,
        )

        return self.open_position(position)

    def close(
        self,
        position_id: str,
        *,
        exit_price: float,
        reason: CloseReason,
        exit_fee_usd: float = 0.0,
    ) -> Position:
        position = self._open_positions.pop(position_id)

        closed = close_position(
            position,
            exit_price=exit_price,
            reason=reason,
            exit_fee_usd=exit_fee_usd,
        )

        self._closed_positions.append(closed)

        return closed

    def get_open_positions(self) -> list[Position]:
        return list(self._open_positions.values())

    def get_closed_positions(self) -> list[Position]:
        return list(self._closed_positions)

    def get_position(self, position_id: str) -> Position | None:
        return self._open_positions.get(position_id)

    def open_count(self) -> int:
        return len(self._open_positions)

    def closed_count(self) -> int:
        return len(self._closed_positions)

    def total_unrealized_pnl(self, mark_price: float) -> float:
        return sum(
            calculate_unrealized_pnl(position, mark_price)
            for position in self._open_positions.values()
        )

    def realized_pnl(self) -> float:
        return sum(position.realized_pnl_usd for position in self._closed_positions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "open_positions": [
                position.model_dump(mode="json")
                for position in self.get_open_positions()
            ],
            "closed_positions": [
                position.model_dump(mode="json")
                for position in self.get_closed_positions()
            ],
            "open_count": self.open_count(),
            "closed_count": self.closed_count(),
            "realized_pnl_usd": self.realized_pnl(),
        }