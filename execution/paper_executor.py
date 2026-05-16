"""
Paper executor for Binance Futures.

Responsabilidades:
- Receber RiskAssessment aprovado.
- Simular preenchimento de ordem.
- Aplicar slippage e fees configuráveis.
- Abrir posição no PositionBook.
- Fechar posição por TP/SL/manual em modo paper.

Este módulo NÃO envia ordem real.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from accounting.positions import (
    CloseReason,
    Position,
    PositionBook,
    check_exit_condition,
)
from risk.risk_manager import OrderRiskPlan, RiskAssessment, should_forward_to_executor


load_dotenv()


PaperExecutionDecision = Literal["FILLED", "REJECTED"]


class PaperExecutionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "paper_executor"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"

    decision: PaperExecutionDecision
    reason: str

    position: dict[str, Any] | None = None
    order_plan: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None

    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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


def apply_entry_slippage(
    *,
    direction: str,
    entry_price: float,
    slippage_pct: float,
) -> float:
    if direction == "LONG":
        return entry_price * (1 + slippage_pct)

    if direction == "SHORT":
        return entry_price * (1 - slippage_pct)

    return entry_price


def apply_exit_slippage(
    *,
    side: str,
    exit_price: float,
    slippage_pct: float,
) -> float:
    if side == "LONG":
        return exit_price * (1 - slippage_pct)

    if side == "SHORT":
        return exit_price * (1 + slippage_pct)

    return exit_price


def reprice_order_plan(
    plan: OrderRiskPlan,
    *,
    filled_entry_price: float,
) -> OrderRiskPlan:
    quantity = plan.notional_usd / filled_entry_price

    if plan.direction == "LONG":
        take_profit_price = filled_entry_price * (1 + plan.tp_move_pct)
        stop_loss_price = filled_entry_price * (1 - plan.sl_move_pct)
    else:
        take_profit_price = filled_entry_price * (1 - plan.tp_move_pct)
        stop_loss_price = filled_entry_price * (1 + plan.sl_move_pct)

    return plan.model_copy(
        update={
            "entry_price": filled_entry_price,
            "quantity": quantity,
            "take_profit_price": take_profit_price,
            "stop_loss_price": stop_loss_price,
        }
    )


class PaperExecutor:
    def __init__(
        self,
        *,
        position_book: PositionBook | None = None,
        slippage_pct: float | None = None,
        entry_fee_usd: float | None = None,
        exit_fee_usd: float | None = None,
    ) -> None:
        self.position_book = position_book or PositionBook()
        self.slippage_pct = (
            slippage_pct
            if slippage_pct is not None
            else env_float("PAPER_EXECUTOR_SLIPPAGE_PCT", 0.0005)
        )
        self.entry_fee_usd = (
            entry_fee_usd
            if entry_fee_usd is not None
            else env_float("PAPER_EXECUTOR_ENTRY_FEE_USD", 0.05)
        )
        self.exit_fee_usd = (
            exit_fee_usd
            if exit_fee_usd is not None
            else env_float("PAPER_EXECUTOR_EXIT_FEE_USD", 0.05)
        )

    def execute(self, assessment: RiskAssessment) -> PaperExecutionResult:
        if not should_forward_to_executor(assessment):
            return PaperExecutionResult(
                decision="REJECTED",
                reason="risk_assessment_not_approved",
                assessment=assessment.model_dump(mode="json"),
            )

        assert assessment.order_plan is not None

        filled_price = apply_entry_slippage(
            direction=assessment.order_plan.direction,
            entry_price=assessment.order_plan.entry_price,
            slippage_pct=self.slippage_pct,
        )

        filled_plan = reprice_order_plan(
            assessment.order_plan,
            filled_entry_price=filled_price,
        )

        position = self.position_book.open_from_order_plan(
            filled_plan,
            entry_fee_usd=self.entry_fee_usd,
            metadata={
                "source": "paper_executor",
                "risk_assessment": assessment.model_dump(mode="json"),
            },
        )

        return PaperExecutionResult(
            decision="FILLED",
            reason="paper_order_filled",
            venue=position.venue,
            symbol=position.symbol,
            position=position.model_dump(mode="json"),
            order_plan=filled_plan.model_dump(mode="json"),
            assessment=assessment.model_dump(mode="json"),
        )

    def update_position_with_price(
        self,
        *,
        position_id: str,
        price: float,
    ) -> Position | None:
        position = self.position_book.get_position(position_id)

        if position is None:
            return None

        reason = check_exit_condition(position, price)

        if reason is None:
            return None

        slipped_exit_price = apply_exit_slippage(
            side=position.side,
            exit_price=price,
            slippage_pct=self.slippage_pct,
        )

        return self.position_book.close(
            position_id,
            exit_price=slipped_exit_price,
            reason=reason,
            exit_fee_usd=self.exit_fee_usd,
        )

    def close_position(
        self,
        *,
        position_id: str,
        exit_price: float,
        reason: CloseReason = "manual",
    ) -> Position:
        position = self.position_book.get_position(position_id)

        if position is None:
            raise KeyError(f"posição não encontrada: {position_id}")

        slipped_exit_price = apply_exit_slippage(
            side=position.side,
            exit_price=exit_price,
            slippage_pct=self.slippage_pct,
        )

        return self.position_book.close(
            position_id,
            exit_price=slipped_exit_price,
            reason=reason,
            exit_fee_usd=self.exit_fee_usd,
        )