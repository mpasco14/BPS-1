"""
Binance Futures orderbook microstructure engine.

Responsabilidades:
- Analisar snapshots de order book da Binance Futures.
- Calcular spread, mid price, weighted mid, depth e imbalance.
- Detectar gaps de liquidez.
- Gerar microstructure_score em [-1, +1].
- Determinar se o book está operável antes de qualquer sinal/execução.

Este módulo NÃO conecta na Binance.
Este módulo NÃO executa ordens.
Este módulo NÃO substitui risk manager.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


Side = Literal["bid", "ask"]


class OrderBookLevel(BaseModel):
    model_config = ConfigDict(extra="allow")

    price: float
    quantity: float

    @field_validator("price")
    @classmethod
    def price_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("price precisa ser maior que zero")

        return float(value)

    @field_validator("quantity")
    @classmethod
    def quantity_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("quantity não pode ser negativo")

        return float(value)

    @property
    def notional(self) -> float:
        return self.price * self.quantity


@dataclass(frozen=True)
class DepthSummary:
    levels: int
    quantity: float
    notional: float


@dataclass(frozen=True)
class OrderBookAnalysis:
    source: str
    venue: str
    symbol: str

    depth_levels: int

    best_bid: float | None
    best_ask: float | None
    mid_price: float | None
    weighted_mid_price: float | None

    spread: float | None
    spread_pct: float | None

    bid_depth_qty: float
    ask_depth_qty: float
    bid_depth_notional: float
    ask_depth_notional: float

    depth_at_5_levels: dict[str, float]

    book_imbalance: float | None
    depth_ratio_signal: float
    weighted_mid_signal: float

    liquidity_gap_bid_pct: float
    liquidity_gap_ask_pct: float
    liquidity_gap_pct: float

    microstructure_score: float

    is_tradeable: bool
    blockers: list[str]

    raw: dict[str, Any] = Field(default_factory=dict)


def clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_orderbook_levels(levels: Any, *, side: Side) -> list[OrderBookLevel]:
    """
    Aceita formatos comuns:

    Binance REST:
      [["60000.0", "1.25"], ...]

    Binance WS:
      [["60000.0", "1.25"], ...]

    Formato interno:
      [{"price": "60000.0", "quantity": "1.25"}, ...]
      [{"price": "60000.0", "qty": "1.25"}, ...]
      [{"price": "60000.0", "size": "1.25"}, ...]
    """
    if not isinstance(levels, list):
        return []

    parsed: list[OrderBookLevel] = []

    for item in levels:
        price = None
        quantity = None

        if isinstance(item, (list, tuple)) and len(item) >= 2:
            price = safe_float(item[0])
            quantity = safe_float(item[1])

        elif isinstance(item, dict):
            price = safe_float(item.get("price") or item.get("p"))
            quantity = safe_float(
                item.get("quantity")
                or item.get("qty")
                or item.get("size")
                or item.get("q")
            )

        if price is None or quantity is None:
            continue

        if price <= 0 or quantity <= 0:
            continue

        parsed.append(OrderBookLevel(price=price, quantity=quantity))

    if side == "bid":
        parsed.sort(key=lambda level: level.price, reverse=True)
    else:
        parsed.sort(key=lambda level: level.price)

    return parsed


def extract_binance_levels(raw: dict[str, Any]) -> tuple[list[OrderBookLevel], list[OrderBookLevel]]:
    """
    Suporta snapshots REST e eventos WS.

    REST:
      {"bids": [...], "asks": [...]}

    WS partial/diff:
      {"b": [...], "a": [...]}
    """
    bid_levels = raw.get("bids", raw.get("b", []))
    ask_levels = raw.get("asks", raw.get("a", []))

    bids = parse_orderbook_levels(bid_levels, side="bid")
    asks = parse_orderbook_levels(ask_levels, side="ask")

    return bids, asks


def calculate_depth(levels: list[OrderBookLevel], top_n: int) -> DepthSummary:
    selected = levels[:top_n]

    quantity = sum(level.quantity for level in selected)
    notional = sum(level.notional for level in selected)

    return DepthSummary(
        levels=len(selected),
        quantity=quantity,
        notional=notional,
    )


def calculate_book_imbalance(
    *,
    bid_notional: float,
    ask_notional: float,
) -> float | None:
    denominator = bid_notional + ask_notional

    if denominator <= 0:
        return None

    return clamp((bid_notional - ask_notional) / denominator)


def calculate_mid_price(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None

    return (best_bid + best_ask) / 2


def calculate_weighted_mid_price(
    *,
    best_bid: float | None,
    best_ask: float | None,
    best_bid_qty: float | None,
    best_ask_qty: float | None,
) -> float | None:
    """
    Microprice/weighted mid baseado no melhor nível.

    Se bid size for maior que ask size, o preço ponderado se aproxima do ask,
    indicando pressão compradora.
    """
    if (
        best_bid is None
        or best_ask is None
        or best_bid_qty is None
        or best_ask_qty is None
    ):
        return None

    denominator = best_bid_qty + best_ask_qty

    if denominator <= 0:
        return None

    return ((best_ask * best_bid_qty) + (best_bid * best_ask_qty)) / denominator


def calculate_spread(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None

    return max(0.0, best_ask - best_bid)


def calculate_spread_pct(
    *,
    spread: float | None,
    mid_price: float | None,
) -> float | None:
    if spread is None or mid_price is None or mid_price <= 0:
        return None

    return spread / mid_price


def calculate_liquidity_gap_pct(levels: list[OrderBookLevel], *, side: Side, top_n: int) -> float:
    selected = levels[:top_n]

    if len(selected) < 2:
        return 0.0

    gaps: list[float] = []

    for current, nxt in zip(selected, selected[1:]):
        if current.price <= 0:
            continue

        if side == "bid":
            gap = (current.price - nxt.price) / current.price
        else:
            gap = (nxt.price - current.price) / current.price

        gaps.append(max(0.0, gap))

    if not gaps:
        return 0.0

    return max(gaps)


def calculate_weighted_mid_signal(
    *,
    weighted_mid_price: float | None,
    mid_price: float | None,
    max_spread_pct: float,
) -> float:
    if weighted_mid_price is None or mid_price is None or mid_price <= 0:
        return 0.0

    deviation_pct = (weighted_mid_price - mid_price) / mid_price

    if max_spread_pct <= 0:
        return 0.0

    return clamp(deviation_pct / max_spread_pct)


def calculate_depth_ratio_signal(
    *,
    bid_notional: float,
    ask_notional: float,
) -> float:
    if bid_notional <= 0 or ask_notional <= 0:
        return 0.0

    return clamp(math.tanh(math.log(bid_notional / ask_notional)))


def calculate_microstructure_score(
    *,
    book_imbalance: float | None,
    weighted_mid_signal: float,
    depth_ratio_signal: float,
    spread_pct: float | None,
    liquidity_gap_pct: float,
    max_spread_pct: float,
    max_liquidity_gap_pct: float,
    weight_imbalance: float,
    weight_weighted_mid: float,
    weight_depth_ratio: float,
) -> float:
    imbalance = book_imbalance or 0.0

    total_weight = weight_imbalance + weight_weighted_mid + weight_depth_ratio

    if total_weight <= 0:
        return 0.0

    raw_score = (
        imbalance * weight_imbalance
        + weighted_mid_signal * weight_weighted_mid
        + depth_ratio_signal * weight_depth_ratio
    ) / total_weight

    spread_penalty = 0.0

    if spread_pct is not None and max_spread_pct > 0:
        spread_penalty = min(spread_pct / max_spread_pct, 1.0)

    gap_penalty = 0.0

    if max_liquidity_gap_pct > 0:
        gap_penalty = min(liquidity_gap_pct / max_liquidity_gap_pct, 1.0)

    quality_multiplier = max(0.0, 1.0 - (spread_penalty * 0.60) - (gap_penalty * 0.40))

    return clamp(raw_score * quality_multiplier)


def analyze_orderbook(
    *,
    bids: list[OrderBookLevel] | None = None,
    asks: list[OrderBookLevel] | None = None,
    raw: dict[str, Any] | None = None,
    symbol: str | None = None,
    venue: str = "binance_futures",
    depth_levels: int | None = None,
    max_spread_pct: float | None = None,
    min_depth_usd: float | None = None,
    max_liquidity_gap_pct: float | None = None,
) -> OrderBookAnalysis:
    raw_payload = raw or {}

    if bids is None or asks is None:
        bids, asks = extract_binance_levels(raw_payload)

    depth_n = int(depth_levels or os.getenv("ORDERBOOK_DEPTH_LEVELS", "5"))

    max_spread = float(max_spread_pct or os.getenv("ORDERBOOK_MAX_SPREAD_PCT", "0.002"))
    min_depth = float(min_depth_usd or os.getenv("ORDERBOOK_MIN_DEPTH_USD", "50000"))
    max_gap = float(max_liquidity_gap_pct or os.getenv("ORDERBOOK_MAX_LIQUIDITY_GAP_PCT", "0.001"))

    weight_imbalance = float(os.getenv("ORDERBOOK_WEIGHT_IMBALANCE", "0.55"))
    weight_weighted_mid = float(os.getenv("ORDERBOOK_WEIGHT_WEIGHTED_MID", "0.25"))
    weight_depth_ratio = float(os.getenv("ORDERBOOK_WEIGHT_DEPTH_RATIO", "0.20"))

    symbol_value = (symbol or raw_payload.get("s") or raw_payload.get("symbol") or os.getenv("ORDERBOOK_SYMBOL", "BTCUSDT")).upper()

    best_bid = bids[0].price if bids else None
    best_ask = asks[0].price if asks else None
    best_bid_qty = bids[0].quantity if bids else None
    best_ask_qty = asks[0].quantity if asks else None

    spread = calculate_spread(best_bid, best_ask)
    mid_price = calculate_mid_price(best_bid, best_ask)
    spread_pct = calculate_spread_pct(spread=spread, mid_price=mid_price)

    weighted_mid = calculate_weighted_mid_price(
        best_bid=best_bid,
        best_ask=best_ask,
        best_bid_qty=best_bid_qty,
        best_ask_qty=best_ask_qty,
    )

    bid_depth = calculate_depth(bids, depth_n)
    ask_depth = calculate_depth(asks, depth_n)

    depth_5_bid = calculate_depth(bids, 5)
    depth_5_ask = calculate_depth(asks, 5)

    book_imbalance = calculate_book_imbalance(
        bid_notional=bid_depth.notional,
        ask_notional=ask_depth.notional,
    )

    liquidity_gap_bid = calculate_liquidity_gap_pct(bids, side="bid", top_n=depth_n)
    liquidity_gap_ask = calculate_liquidity_gap_pct(asks, side="ask", top_n=depth_n)
    liquidity_gap = max(liquidity_gap_bid, liquidity_gap_ask)

    weighted_mid_signal = calculate_weighted_mid_signal(
        weighted_mid_price=weighted_mid,
        mid_price=mid_price,
        max_spread_pct=max_spread,
    )

    depth_ratio_signal = calculate_depth_ratio_signal(
        bid_notional=bid_depth.notional,
        ask_notional=ask_depth.notional,
    )

    blockers: list[str] = []

    if not bids or not asks:
        blockers.append("empty_orderbook")

    if spread_pct is None:
        blockers.append("missing_spread")
    elif spread_pct > max_spread:
        blockers.append("spread_too_wide")

    min_side_depth = min(bid_depth.notional, ask_depth.notional)

    if min_side_depth < min_depth:
        blockers.append("insufficient_depth")

    if liquidity_gap > max_gap:
        blockers.append("liquidity_gap_too_large")

    score = calculate_microstructure_score(
        book_imbalance=book_imbalance,
        weighted_mid_signal=weighted_mid_signal,
        depth_ratio_signal=depth_ratio_signal,
        spread_pct=spread_pct,
        liquidity_gap_pct=liquidity_gap,
        max_spread_pct=max_spread,
        max_liquidity_gap_pct=max_gap,
        weight_imbalance=weight_imbalance,
        weight_weighted_mid=weight_weighted_mid,
        weight_depth_ratio=weight_depth_ratio,
    )

    return OrderBookAnalysis(
        source="orderbook_engine",
        venue=venue,
        symbol=symbol_value,
        depth_levels=depth_n,
        best_bid=best_bid,
        best_ask=best_ask,
        mid_price=mid_price,
        weighted_mid_price=weighted_mid,
        spread=spread,
        spread_pct=spread_pct,
        bid_depth_qty=bid_depth.quantity,
        ask_depth_qty=ask_depth.quantity,
        bid_depth_notional=bid_depth.notional,
        ask_depth_notional=ask_depth.notional,
        depth_at_5_levels={
            "bid_qty": depth_5_bid.quantity,
            "ask_qty": depth_5_ask.quantity,
            "bid_notional": depth_5_bid.notional,
            "ask_notional": depth_5_ask.notional,
        },
        book_imbalance=book_imbalance,
        depth_ratio_signal=depth_ratio_signal,
        weighted_mid_signal=weighted_mid_signal,
        liquidity_gap_bid_pct=liquidity_gap_bid,
        liquidity_gap_ask_pct=liquidity_gap_ask,
        liquidity_gap_pct=liquidity_gap,
        microstructure_score=score,
        is_tradeable=len(blockers) == 0,
        blockers=blockers,
        raw=raw_payload,
    )


def analysis_to_dict(analysis: OrderBookAnalysis) -> dict[str, Any]:
    return asdict(analysis)