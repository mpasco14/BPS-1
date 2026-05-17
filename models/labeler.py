"""
TP/SL/time-barrier labeler for Binance Futures.

Responsabilidades:
- Criar labels para treinamento de modelos.
- Verificar se TP ou SL foi atingido primeiro.
- Usar regra conservadora quando TP e SL ocorrem no mesmo candle.
- Produzir target para modelos:
  1 = TP antes do SL
  0 = SL antes do TP
  None = nenhum dos dois dentro do horizonte

Este módulo NÃO treina modelo.
Este módulo NÃO executa ordens.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


Side = Literal["LONG", "SHORT"]
Outcome = Literal["take_profit", "stop_loss", "time_barrier", "no_data"]


class PricePoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: Any | None = None

    high: float
    low: float
    close: float

    open: float | None = None
    mark_price: float | None = None

    @field_validator("high", "low", "close")
    @classmethod
    def positive_price(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("preço precisa ser maior que zero")
        return float(value)


class BarrierLabel(BaseModel):
    model_config = ConfigDict(extra="allow")

    side: Side

    entry_price: float
    take_profit_price: float
    stop_loss_price: float

    outcome: Outcome
    target: int | None

    exit_price: float
    outcome_timestamp: Any | None = None
    time_to_outcome_seconds: float | None = None

    ambiguous_same_bar: bool = False
    conservative_on_ambiguous: bool = True

    gross_pnl_usd: float | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


def parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def timestamp_to_seconds(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return int(value.astimezone(timezone.utc).timestamp())

    if isinstance(value, int | float):
        numeric = int(value)

        if numeric >= 1_000_000_000_000:
            numeric = numeric // 1000

        return numeric

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return None

        if stripped.isdigit():
            return timestamp_to_seconds(int(stripped))

        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return int(parsed.astimezone(timezone.utc).timestamp())
        except ValueError:
            return None

    return None


def normalize_price_path(path: list[dict[str, Any]] | list[PricePoint]) -> list[PricePoint]:
    points = [
        item if isinstance(item, PricePoint) else PricePoint.model_validate(item)
        for item in path
    ]

    if all(timestamp_to_seconds(point.timestamp) is not None for point in points):
        points.sort(key=lambda point: timestamp_to_seconds(point.timestamp) or 0)

    return points


def calculate_barrier_prices(
    *,
    side: Side,
    entry_price: float,
    tp_move_pct: float,
    sl_move_pct: float,
) -> tuple[float, float]:
    if side == "LONG":
        return (
            entry_price * (1 + tp_move_pct),
            entry_price * (1 - sl_move_pct),
        )

    return (
        entry_price * (1 - tp_move_pct),
        entry_price * (1 + sl_move_pct),
    )


def gross_pnl_from_exit(
    *,
    side: Side,
    entry_price: float,
    exit_price: float,
    quantity: float,
) -> float:
    if side == "LONG":
        return (exit_price - entry_price) * quantity

    return (entry_price - exit_price) * quantity


def get_max_holding_seconds(timeframe: str) -> int | None:
    mapping = {
        "5m": "LABELER_MAX_HOLDING_SECONDS_5M",
        "15m": "LABELER_MAX_HOLDING_SECONDS_15M",
        "1h": "LABELER_MAX_HOLDING_SECONDS_1H",
        "1d": "LABELER_MAX_HOLDING_SECONDS_1D",
    }

    env_name = mapping.get(timeframe)

    if env_name is None:
        return None

    value = os.getenv(env_name)

    if value is None:
        return None

    return int(value)


def label_price_path(
    *,
    side: Side,
    entry_price: float,
    price_path: list[dict[str, Any]] | list[PricePoint],
    take_profit_price: float | None = None,
    stop_loss_price: float | None = None,
    tp_move_pct: float | None = None,
    sl_move_pct: float | None = None,
    quantity: float | None = None,
    entry_timestamp: Any | None = None,
    max_holding_seconds: int | None = None,
    conservative_on_ambiguous: bool | None = None,
    timeframe: str | None = None,
) -> BarrierLabel:
    if take_profit_price is None or stop_loss_price is None:
        if tp_move_pct is None or sl_move_pct is None:
            raise ValueError("forneça TP/SL explícitos ou tp_move_pct/sl_move_pct")

        take_profit_price, stop_loss_price = calculate_barrier_prices(
            side=side,
            entry_price=entry_price,
            tp_move_pct=tp_move_pct,
            sl_move_pct=sl_move_pct,
        )

    conservative = (
        conservative_on_ambiguous
        if conservative_on_ambiguous is not None
        else parse_bool(os.getenv("LABELER_CONSERVATIVE_ON_AMBIGUOUS"), default=True)
    )

    if max_holding_seconds is None and timeframe is not None:
        max_holding_seconds = get_max_holding_seconds(timeframe)

    points = normalize_price_path(price_path)

    if not points:
        return BarrierLabel(
            side=side,
            entry_price=entry_price,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            outcome="no_data",
            target=None,
            exit_price=entry_price,
            conservative_on_ambiguous=conservative,
        )

    entry_ts = timestamp_to_seconds(entry_timestamp)

    if entry_ts is None:
        entry_ts = timestamp_to_seconds(points[0].timestamp)

    eligible_points: list[PricePoint] = []

    for point in points:
        point_ts = timestamp_to_seconds(point.timestamp)

        if entry_ts is not None and point_ts is not None:
            elapsed = point_ts - entry_ts

            if elapsed < 0:
                continue

            if max_holding_seconds is not None and elapsed > max_holding_seconds:
                break

        eligible_points.append(point)

    if not eligible_points:
        return BarrierLabel(
            side=side,
            entry_price=entry_price,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            outcome="no_data",
            target=None,
            exit_price=entry_price,
            conservative_on_ambiguous=conservative,
        )

    for point in eligible_points:
        point_ts = timestamp_to_seconds(point.timestamp)
        time_to_outcome = None

        if entry_ts is not None and point_ts is not None:
            time_to_outcome = max(0, point_ts - entry_ts)

        if side == "LONG":
            hit_tp = point.high >= take_profit_price
            hit_sl = point.low <= stop_loss_price
        else:
            hit_tp = point.low <= take_profit_price
            hit_sl = point.high >= stop_loss_price

        if hit_tp and hit_sl:
            outcome = "stop_loss" if conservative else "take_profit"
            target = 0 if conservative else 1
            exit_price = stop_loss_price if conservative else take_profit_price

            gross_pnl = None
            if quantity is not None:
                gross_pnl = gross_pnl_from_exit(
                    side=side,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    quantity=quantity,
                )

            return BarrierLabel(
                side=side,
                entry_price=entry_price,
                take_profit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
                outcome=outcome,
                target=target,
                exit_price=exit_price,
                outcome_timestamp=point.timestamp,
                time_to_outcome_seconds=time_to_outcome,
                ambiguous_same_bar=True,
                conservative_on_ambiguous=conservative,
                gross_pnl_usd=gross_pnl,
            )

        if hit_tp:
            gross_pnl = None
            if quantity is not None:
                gross_pnl = gross_pnl_from_exit(
                    side=side,
                    entry_price=entry_price,
                    exit_price=take_profit_price,
                    quantity=quantity,
                )

            return BarrierLabel(
                side=side,
                entry_price=entry_price,
                take_profit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
                outcome="take_profit",
                target=1,
                exit_price=take_profit_price,
                outcome_timestamp=point.timestamp,
                time_to_outcome_seconds=time_to_outcome,
                conservative_on_ambiguous=conservative,
                gross_pnl_usd=gross_pnl,
            )

        if hit_sl:
            gross_pnl = None
            if quantity is not None:
                gross_pnl = gross_pnl_from_exit(
                    side=side,
                    entry_price=entry_price,
                    exit_price=stop_loss_price,
                    quantity=quantity,
                )

            return BarrierLabel(
                side=side,
                entry_price=entry_price,
                take_profit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
                outcome="stop_loss",
                target=0,
                exit_price=stop_loss_price,
                outcome_timestamp=point.timestamp,
                time_to_outcome_seconds=time_to_outcome,
                conservative_on_ambiguous=conservative,
                gross_pnl_usd=gross_pnl,
            )

    last_point = eligible_points[-1]
    gross_pnl = None

    if quantity is not None:
        gross_pnl = gross_pnl_from_exit(
            side=side,
            entry_price=entry_price,
            exit_price=last_point.close,
            quantity=quantity,
        )

    last_ts = timestamp_to_seconds(last_point.timestamp)
    time_to_outcome = None

    if entry_ts is not None and last_ts is not None:
        time_to_outcome = max(0, last_ts - entry_ts)

    return BarrierLabel(
        side=side,
        entry_price=entry_price,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
        outcome="time_barrier",
        target=None,
        exit_price=last_point.close,
        outcome_timestamp=last_point.timestamp,
        time_to_outcome_seconds=time_to_outcome,
        conservative_on_ambiguous=conservative,
        gross_pnl_usd=gross_pnl,
    )


def label_to_dict(label: BarrierLabel) -> dict[str, Any]:
    return label.model_dump(mode="json")