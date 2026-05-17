"""
Binance Futures limit order builder.

Responsabilidades:
- Construir payload de ordem LIMIT para Binance Futures.
- Aplicar tickSize, stepSize e minNotional.
- Adaptar OrderRiskPlan para ordem Binance.

Este módulo NÃO envia ordem.
"""

from __future__ import annotations

import os
import time
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from risk.risk_manager import OrderRiskPlan


load_dotenv()


OrderSide = Literal["BUY", "SELL"]


class SymbolTradingRules(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str

    tick_size: float
    step_size: float

    tick_size_raw: str | None = None
    step_size_raw: str | None = None

    min_qty: float = 0.0
    min_notional: float = 0.0

    raw_filters: list[dict[str, Any]] = Field(default_factory=list)


class LimitOrderPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    side: OrderSide
    type: str = "LIMIT"
    timeInForce: str = "GTC"

    quantity: str
    price: str

    newClientOrderId: str
    newOrderRespType: str = "ACK"

    reduceOnly: str | None = None
    goodTillDate: int | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


def decimal_places(value: float | str) -> int:
    """
    Preserva casas decimais de strings como '0.10'.

    Não usar normalize(), porque Decimal('0.10').normalize()
    vira Decimal('0.1') e perdemos uma casa decimal.
    """
    dec = Decimal(str(value))

    if dec.as_tuple().exponent >= 0:
        return 0

    return abs(dec.as_tuple().exponent)


def decimal_from_float(value: float) -> Decimal:
    """
    Converte float para Decimal removendo ruído binário.

    Exemplo:
    60000 * 1.001 pode virar 60059.99999999999.
    Com round(value, 12), voltamos para 60060.0 antes do Decimal.
    """
    return Decimal(str(round(float(value), 12)))


def format_decimal(value: float, step: float | str) -> str:
    places = decimal_places(step)

    return f"{value:.{places}f}"


def round_to_step(
    value: float,
    step: float,
    *,
    mode: Literal["down", "up"] = "down",
) -> float:
    if step <= 0:
        return float(value)

    decimal_value = decimal_from_float(value)
    decimal_step = Decimal(str(step))

    rounding = ROUND_DOWN if mode == "down" else ROUND_UP

    rounded = (decimal_value / decimal_step).to_integral_value(rounding=rounding) * decimal_step

    return float(rounded)


def round_quantity(
    quantity: float,
    step_size: float,
) -> float:
    return round_to_step(quantity, step_size, mode="down")


def round_price_for_side(
    price: float,
    tick_size: float,
    side: OrderSide,
) -> float:
    if side == "BUY":
        return round_to_step(price, tick_size, mode="down")

    return round_to_step(price, tick_size, mode="up")


def find_filter(filters: list[dict[str, Any]], filter_type: str) -> dict[str, Any]:
    for item in filters:
        if item.get("filterType") == filter_type:
            return item

    return {}


def rules_from_symbol_info(symbol_info: dict[str, Any]) -> SymbolTradingRules:
    filters = list(symbol_info.get("filters") or [])

    price_filter = find_filter(filters, "PRICE_FILTER")
    lot_size = find_filter(filters, "LOT_SIZE")
    market_lot_size = find_filter(filters, "MARKET_LOT_SIZE")
    min_notional_filter = find_filter(filters, "MIN_NOTIONAL")
    notional_filter = find_filter(filters, "NOTIONAL")

    step_source = lot_size or market_lot_size

    min_notional = (
        min_notional_filter.get("notional")
        or min_notional_filter.get("minNotional")
        or notional_filter.get("minNotional")
        or 0
    )

    tick_size_raw = str(price_filter.get("tickSize", "0.1"))
    step_size_raw = str(step_source.get("stepSize", "0.001"))

    return SymbolTradingRules(
        symbol=str(symbol_info["symbol"]).upper(),
        tick_size=float(tick_size_raw),
        step_size=float(step_size_raw),
        tick_size_raw=tick_size_raw,
        step_size_raw=step_size_raw,
        min_qty=float(step_source.get("minQty", 0.0)),
        min_notional=float(min_notional),
        raw_filters=filters,
    )


def client_order_id(
    *,
    symbol: str,
    side: OrderSide,
    prefix: str | None = None,
) -> str:
    resolved_prefix = prefix or os.getenv("BINANCE_CLIENT_ORDER_ID_PREFIX", "btc_poly_bot")
    stamp = int(time.time() * 1000)

    raw = f"{resolved_prefix}_{symbol}_{side}_{stamp}"

    return raw[:36]


def calculate_entry_limit_price(
    *,
    plan: OrderRiskPlan,
    slippage_pct: float,
) -> float:
    entry = Decimal(str(plan.entry_price))
    slippage = Decimal(str(slippage_pct))

    if plan.direction == "LONG":
        price = entry * (Decimal("1") + slippage)
    else:
        price = entry * (Decimal("1") - slippage)

    # Remove ruídos e mantém precisão suficiente para tickSize.
    price = price.quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)

    return float(price)


def build_limit_order_from_plan(
    *,
    plan: OrderRiskPlan,
    rules: SymbolTradingRules,
    slippage_pct: float | None = None,
    time_in_force: str | None = None,
    reduce_only: bool | None = None,
    good_till_date: int | None = None,
) -> LimitOrderPayload:
    slippage = slippage_pct
    if slippage is None:
        slippage = float(os.getenv("BINANCE_ENTRY_SLIPPAGE_MAX_PCT", "0.0005"))

    side: OrderSide = "BUY" if plan.direction == "LONG" else "SELL"

    raw_price = calculate_entry_limit_price(
        plan=plan,
        slippage_pct=slippage,
    )

    rounded_price = round_price_for_side(
        raw_price,
        rules.tick_size,
        side,
    )

    rounded_qty = round_quantity(
        plan.quantity,
        rules.step_size,
    )

    if rounded_qty <= 0:
        raise ValueError("quantity arredondada ficou inválida.")

    if rules.min_qty and rounded_qty < rules.min_qty:
        raise ValueError("quantity abaixo de minQty.")

    notional = rounded_qty * rounded_price

    if rules.min_notional and notional < rules.min_notional:
        raise ValueError("notional abaixo de minNotional.")

    tif = time_in_force or os.getenv("BINANCE_DEFAULT_TIME_IN_FORCE", "GTC")

    payload = LimitOrderPayload(
        symbol=plan.symbol.upper(),
        side=side,
        timeInForce=tif,
        quantity=format_decimal(rounded_qty, rules.step_size_raw or rules.step_size),
        price=format_decimal(rounded_price, rules.tick_size_raw or rules.tick_size),
        newClientOrderId=client_order_id(
            symbol=plan.symbol.upper(),
            side=side,
        ),
        reduceOnly=str(reduce_only).lower() if reduce_only is not None else None,
        goodTillDate=good_till_date,
        metadata={
            "source": "limit_order",
            "direction": plan.direction,
            "entry_price": plan.entry_price,
            "raw_limit_price": raw_price,
            "slippage_pct": slippage,
            "notional_after_rounding": notional,
        },
    )

    return payload


def limit_order_to_params(payload: LimitOrderPayload) -> dict[str, Any]:
    data = payload.model_dump(mode="python")
    data.pop("metadata", None)

    return {
        key: value
        for key, value in data.items()
        if value is not None
    }