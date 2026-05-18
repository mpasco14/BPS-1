"""
Binance Futures fill monitor.

Responsabilidades:
- Normalizar eventos ORDER_TRADE_UPDATE do User Data Stream.
- Detectar partial fill, full fill, cancelamento e expiração.
- Decidir se mantém ou cancela o restante em fill parcial.
- Atualizar exposição com base em fills.

Este módulo NÃO abre WebSocket diretamente nesta etapa.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from risk.exposure import ExposureSnapshot, apply_fill_to_exposure


load_dotenv()


FillAction = Literal["NO_ACTION", "WAIT", "KEEP_REST", "CANCEL_REST"]


class BinanceOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_user_data_stream"

    event_type: str
    event_time: int | None = None
    transaction_time: int | None = None

    symbol: str
    client_order_id: str | None = None
    order_id: int | None = None

    side: str
    order_type: str | None = None
    execution_type: str
    order_status: str

    original_qty: float
    last_filled_qty: float
    cumulative_filled_qty: float

    last_filled_price: float
    average_price: float | None = None

    commission_asset: str | None = None
    commission: float = 0.0

    realized_pnl: float = 0.0

    raw: dict[str, Any] = Field(default_factory=dict)


class FillDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: FillAction
    reason: str

    fill_ratio: float
    edge_valid: bool

    update: dict[str, Any] = Field(default_factory=dict)


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_order_trade_update(payload: dict[str, Any]) -> BinanceOrderUpdate:
    """
    Normaliza evento ORDER_TRADE_UPDATE.

    Estrutura típica:
    {
      "e": "ORDER_TRADE_UPDATE",
      "E": ...,
      "T": ...,
      "o": {
        "s": "BTCUSDT",
        "c": "clientOrderId",
        "S": "BUY",
        "o": "LIMIT",
        "x": "TRADE",
        "X": "PARTIALLY_FILLED",
        "q": "0.010",
        "l": "0.005",
        "z": "0.005",
        "L": "60000",
        ...
      }
    }
    """
    order = payload.get("o") or {}

    return BinanceOrderUpdate(
        event_type=str(payload.get("e", "")),
        event_time=safe_int(payload.get("E")),
        transaction_time=safe_int(payload.get("T") or order.get("T")),
        symbol=str(order.get("s", "")).upper(),
        client_order_id=order.get("c"),
        order_id=safe_int(order.get("i")),
        side=str(order.get("S", "")),
        order_type=order.get("o"),
        execution_type=str(order.get("x", "")),
        order_status=str(order.get("X", "")),
        original_qty=safe_float(order.get("q")),
        last_filled_qty=safe_float(order.get("l")),
        cumulative_filled_qty=safe_float(order.get("z")),
        last_filled_price=safe_float(order.get("L")),
        average_price=safe_float(order.get("ap")) if order.get("ap") is not None else None,
        commission_asset=order.get("N"),
        commission=safe_float(order.get("n")),
        realized_pnl=safe_float(order.get("rp")),
        raw=payload,
    )


def fill_ratio(update: BinanceOrderUpdate) -> float:
    if update.original_qty <= 0:
        return 0.0

    return min(1.0, update.cumulative_filled_qty / update.original_qty)


def is_trade_execution(update: BinanceOrderUpdate) -> bool:
    return update.execution_type == "TRADE" and update.last_filled_qty > 0


def is_partial_fill(update: BinanceOrderUpdate) -> bool:
    return update.order_status == "PARTIALLY_FILLED" and update.cumulative_filled_qty > 0


def is_full_fill(update: BinanceOrderUpdate) -> bool:
    return update.order_status == "FILLED"


def is_cancelled_or_expired(update: BinanceOrderUpdate) -> bool:
    return update.order_status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED"}


def min_partial_keep_ratio() -> float:
    return float(os.getenv("FILL_MONITOR_PARTIAL_FILL_KEEP_RATIO", "0.60"))


def decide_partial_fill_action(
    update: BinanceOrderUpdate,
    *,
    edge_valid: bool,
    min_keep_ratio: float | None = None,
) -> FillDecision:
    ratio = fill_ratio(update)
    threshold = min_keep_ratio if min_keep_ratio is not None else min_partial_keep_ratio()

    if not is_partial_fill(update):
        return FillDecision(
            action="NO_ACTION",
            reason="not_partial_fill",
            fill_ratio=ratio,
            edge_valid=edge_valid,
            update=update.model_dump(mode="json"),
        )

    if not edge_valid:
        return FillDecision(
            action="CANCEL_REST",
            reason="edge_lost_after_partial_fill",
            fill_ratio=ratio,
            edge_valid=edge_valid,
            update=update.model_dump(mode="json"),
        )

    if ratio >= threshold:
        return FillDecision(
            action="KEEP_REST",
            reason="partial_fill_above_threshold_and_edge_valid",
            fill_ratio=ratio,
            edge_valid=edge_valid,
            update=update.model_dump(mode="json"),
        )

    return FillDecision(
        action="WAIT",
        reason="partial_fill_below_threshold_but_edge_valid",
        fill_ratio=ratio,
        edge_valid=edge_valid,
        update=update.model_dump(mode="json"),
    )


def direction_from_side(side: str) -> Literal["LONG", "SHORT"]:
    return "LONG" if side.upper() == "BUY" else "SHORT"


def margin_from_fill(
    update: BinanceOrderUpdate,
    *,
    leverage: float | None = None,
) -> float:
    lev = leverage if leverage is not None else float(os.getenv("FILL_MONITOR_DEFAULT_LEVERAGE", "30"))

    if lev <= 0:
        return 0.0

    notional = update.last_filled_qty * update.last_filled_price

    return notional / lev


def apply_fill_update_to_exposure(
    snapshot: ExposureSnapshot,
    update: BinanceOrderUpdate,
    *,
    timeframe: str | None = None,
    leverage: float | None = None,
) -> ExposureSnapshot:
    if not is_trade_execution(update):
        return snapshot

    margin_usd = margin_from_fill(update, leverage=leverage)

    if margin_usd <= 0:
        return snapshot

    return apply_fill_to_exposure(
        snapshot,
        symbol=update.symbol,
        timeframe=timeframe or os.getenv("FILL_MONITOR_DEFAULT_TIMEFRAME", "5m"),
        direction=direction_from_side(update.side),
        margin_usd=margin_usd,
    )


def fill_update_to_dict(update: BinanceOrderUpdate) -> dict[str, Any]:
    return update.model_dump(mode="json")


def fill_decision_to_dict(decision: FillDecision) -> dict[str, Any]:
    return decision.model_dump(mode="json")