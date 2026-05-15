"""
Data Normalizer.

Responsabilidades:
- Validar dados brutos vindos dos conectores.
- Converter timestamps para UTC.
- Converter preços, volumes e scores para float.
- Padronizar schemas de candle, orderbook, on-chain e sentiment.
- Aplicar forward-fill somente em campos seguros.

Este módulo NÃO coleta dados externos.
Este módulo NÃO executa ordens.
Este módulo NÃO grava no banco nesta etapa.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


load_dotenv()


EventKind = Literal["candle", "orderbook", "onchain", "sentiment"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def unix_now_seconds() -> int:
    return int(time.time())


def parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []

    return [item.strip() for item in value.split(",") if item.strip()]


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def timestamp_to_utc_iso(value: Any) -> str:
    """
    Converte timestamps variados para ISO UTC.

    Aceita:
    - ISO string
    - Unix seconds
    - Unix milliseconds
    - None, usando agora
    """
    if value is None:
        return utc_now_iso()

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return utc_now_iso()

        # Número em string.
        if stripped.isdigit():
            return timestamp_to_utc_iso(int(stripped))

        # ISO string.
        normalized = stripped.replace("Z", "+00:00")

        try:
            parsed = datetime.fromisoformat(normalized)

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return utc_now_iso()

    numeric = safe_int(value)

    if numeric is None:
        return utc_now_iso()

    # Heurística:
    # >= 10^12 provavelmente é Unix milliseconds.
    if numeric >= 1_000_000_000_000:
        numeric = numeric // 1000

    return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()


def normalize_symbol(value: str) -> str:
    value = value.strip().upper()

    if not value:
        raise ValueError("symbol não pode ser vazio")

    return value


def normalize_timeframe(value: str) -> str:
    value = value.strip()

    aliases = {
        "1D": "1d",
        "1d": "1d",
        "1H": "1h",
        "1h": "1h",
        "15M": "15m",
        "15m": "15m",
        "5M": "5m",
        "5m": "5m",
    }

    normalized = aliases.get(value)

    if normalized is None:
        raise ValueError(f"timeframe inválido: {value}")

    return normalized


class NormalizedBaseEvent(BaseModel):
    """
    Base comum para todos os eventos normalizados.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    event_kind: EventKind
    source: str
    provider: str | None = None

    event_time: str
    received_at: str | None = None
    normalized_at: str = Field(default_factory=utc_now_iso)

    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedCandleEvent(NormalizedBaseEvent):
    event_kind: Literal["candle"] = "candle"

    exchange: str
    market_type: str
    symbol: str
    timeframe: str

    open_time: str
    close_time: str

    open: float
    high: float
    low: float
    close: float
    volume: float

    quote_volume: float | None = None
    trades_count: int | None = None
    taker_buy_base_volume: float | None = None
    taker_buy_quote_volume: float | None = None

    is_closed: bool

    funding_rate: float | None = None
    open_interest: float | None = None
    mark_price: float | None = None
    index_price: float | None = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        return normalize_timeframe(value)

    @field_validator("open", "high", "low", "close")
    @classmethod
    def price_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("preço precisa ser maior que zero")

        return float(value)

    @field_validator("volume")
    @classmethod
    def volume_must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("volume não pode ser negativo")

        return float(value)


class NormalizedOrderbookEvent(NormalizedBaseEvent):
    event_kind: Literal["orderbook"] = "orderbook"

    market: str | None = None
    market_id: str | None = None
    asset_id: str | None = None
    token_id: str | None = None

    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    mid_price: float | None = None

    liquidity: float | None = None
    bid_depth: float | None = None
    ask_depth: float | None = None

    event_type: str | None = None


class NormalizedOnchainEvent(NormalizedBaseEvent):
    event_kind: Literal["onchain"] = "onchain"

    asset: str
    category: str
    metric: str
    interval: str

    value: Any
    score: float | None = None

    @field_validator("asset")
    @classmethod
    def validate_asset(cls, value: str) -> str:
        return value.strip().upper()


class NormalizedSentimentEvent(NormalizedBaseEvent):
    event_kind: Literal["sentiment"] = "sentiment"

    asset: str
    category: str
    interval: str

    sentiment_score: float
    volume_mentions: int
    keywords: list[str] = Field(default_factory=list)
    positive_hits: list[str] = Field(default_factory=list)
    negative_hits: list[str] = Field(default_factory=list)
    neutral_hits: list[str] = Field(default_factory=list)

    @field_validator("asset")
    @classmethod
    def validate_asset(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("sentiment_score")
    @classmethod
    def score_range(cls, value: float) -> float:
        if value < -1 or value > 1:
            raise ValueError("sentiment_score deve estar entre -1 e 1")

        return float(value)

    @field_validator("volume_mentions")
    @classmethod
    def mentions_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("volume_mentions não pode ser negativo")

        return value


def normalize_candle_event(raw: dict[str, Any]) -> NormalizedCandleEvent:
    """
    Normaliza evento vindo de btc-candles.
    """
    return NormalizedCandleEvent(
        source=str(raw.get("source") or "unknown"),
        provider=str(raw.get("exchange") or "binance"),
        exchange=str(raw.get("exchange") or "binance"),
        market_type=str(raw.get("market_type") or "unknown"),
        symbol=str(raw.get("symbol") or ""),
        timeframe=str(raw.get("timeframe") or ""),
        event_time=timestamp_to_utc_iso(raw.get("event_time") or raw.get("close_time")),
        received_at=timestamp_to_utc_iso(raw.get("received_at")),
        open_time=timestamp_to_utc_iso(raw.get("open_time")),
        close_time=timestamp_to_utc_iso(raw.get("close_time")),
        open=float(raw.get("open")),
        high=float(raw.get("high")),
        low=float(raw.get("low")),
        close=float(raw.get("close")),
        volume=float(raw.get("volume")),
        quote_volume=safe_float(raw.get("quote_volume")),
        trades_count=safe_int(raw.get("trades_count")),
        taker_buy_base_volume=safe_float(raw.get("taker_buy_base_volume")),
        taker_buy_quote_volume=safe_float(raw.get("taker_buy_quote_volume")),
        is_closed=bool(raw.get("is_closed")),
        funding_rate=safe_float(raw.get("funding_rate")),
        open_interest=safe_float(raw.get("open_interest")),
        mark_price=safe_float(raw.get("mark_price")),
        index_price=safe_float(raw.get("index_price")),
        raw=raw,
    )


def normalize_orderbook_event(raw: dict[str, Any]) -> NormalizedOrderbookEvent:
    """
    Normaliza evento vindo de poly-orderbook.
    """
    best_bid = safe_float(raw.get("best_bid"))
    best_ask = safe_float(raw.get("best_ask"))
    spread = safe_float(raw.get("spread"))

    if spread is None and best_bid is not None and best_ask is not None:
        spread = round(best_ask - best_bid, 10)

    mid_price = safe_float(raw.get("mid_price"))

    if mid_price is None and best_bid is not None and best_ask is not None:
        mid_price = round((best_bid + best_ask) / 2, 10)

    return NormalizedOrderbookEvent(
        source=str(raw.get("source") or "polymarket_ws"),
        provider="polymarket",
        event_time=timestamp_to_utc_iso(raw.get("timestamp") or raw.get("received_at")),
        received_at=timestamp_to_utc_iso(raw.get("received_at")),
        market=raw.get("market"),
        market_id=raw.get("market_id") or raw.get("market"),
        asset_id=raw.get("asset_id"),
        token_id=raw.get("token_id") or raw.get("asset_id"),
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        mid_price=mid_price,
        liquidity=safe_float(raw.get("liquidity")),
        bid_depth=safe_float(raw.get("bid_depth")),
        ask_depth=safe_float(raw.get("ask_depth")),
        event_type=raw.get("event_type"),
        raw=raw,
    )


def normalize_onchain_event(raw: dict[str, Any]) -> NormalizedOnchainEvent:
    """
    Normaliza evento vindo de onchain-events.
    """
    event_type = str(raw.get("event_type") or raw.get("metric") or "unknown")

    return NormalizedOnchainEvent(
        source=str(raw.get("source") or "onchain"),
        provider=str(raw.get("provider") or raw.get("source") or "unknown"),
        event_time=timestamp_to_utc_iso(raw.get("timestamp") or raw.get("collected_at")),
        received_at=timestamp_to_utc_iso(raw.get("collected_at")),
        asset=str(raw.get("asset") or "BTC"),
        category=str(raw.get("category") or "unknown"),
        metric=event_type,
        interval=str(raw.get("interval") or "snapshot"),
        value=raw.get("value"),
        score=safe_float(raw.get("score")),
        raw=raw,
    )


def normalize_sentiment_event(raw: dict[str, Any]) -> NormalizedSentimentEvent:
    """
    Normaliza evento vindo de sentiment-events.
    """
    return NormalizedSentimentEvent(
        source=str(raw.get("source") or "sentiment"),
        provider=str(raw.get("provider") or "unknown"),
        event_time=timestamp_to_utc_iso(raw.get("timestamp") or raw.get("collected_at")),
        received_at=timestamp_to_utc_iso(raw.get("collected_at")),
        asset=str(raw.get("asset") or "BTC"),
        category=str(raw.get("category") or "social_news_sentiment"),
        interval=str(raw.get("interval") or "snapshot"),
        sentiment_score=float(raw.get("sentiment_score")),
        volume_mentions=int(raw.get("volume_mentions")),
        keywords=list(raw.get("keywords") or []),
        positive_hits=list(raw.get("positive_hits") or []),
        negative_hits=list(raw.get("negative_hits") or []),
        neutral_hits=list(raw.get("neutral_hits") or []),
        raw=raw,
    )


def infer_event_kind(raw: dict[str, Any]) -> EventKind:
    """
    Infere o tipo do evento bruto.
    """
    if "open_time" in raw and "close_time" in raw and "timeframe" in raw:
        return "candle"

    if "sentiment_score" in raw and "volume_mentions" in raw:
        return "sentiment"

    if raw.get("source") == "free_onchain" or raw.get("provider") in {"mempool_space", "defillama"}:
        return "onchain"

    if "best_bid" in raw or "best_ask" in raw or raw.get("channel") == "market":
        return "orderbook"

    raise ValueError("Não foi possível inferir o tipo do evento")


def normalize_event(raw: dict[str, Any], event_kind: EventKind | None = None) -> NormalizedBaseEvent:
    """
    Normaliza qualquer evento bruto suportado.
    """
    kind = event_kind or infer_event_kind(raw)

    if kind == "candle":
        return normalize_candle_event(raw)

    if kind == "orderbook":
        return normalize_orderbook_event(raw)

    if kind == "onchain":
        return normalize_onchain_event(raw)

    if kind == "sentiment":
        return normalize_sentiment_event(raw)

    raise ValueError(f"Tipo de evento não suportado: {kind}")


class ForwardFillState:
    """
    Estado simples para forward-fill controlado.

    Usar somente em campos permitidos.
    """

    def __init__(
        self,
        *,
        allowed_fields: list[str] | None = None,
        max_age_seconds: int | None = None,
    ) -> None:
        self.allowed_fields = set(
            allowed_fields
            or parse_csv_env(
                os.getenv(
                    "NORMALIZER_FORWARD_FILL_FIELDS",
                    "funding_rate,open_interest,mark_price,index_price,fee_pressure_score,mempool_congestion_score,stablecoin_liquidity_score,sentiment_score",
                )
            )
        )

        self.max_age_seconds = int(
            max_age_seconds
            or os.getenv("NORMALIZER_FORWARD_FILL_MAX_AGE_SECONDS", "3600")
        )

        self._state: dict[str, dict[str, tuple[Any, int]]] = {}

    def update_and_fill(
        self,
        *,
        entity_key: str,
        values: dict[str, Any],
        now: int | None = None,
    ) -> dict[str, Any]:
        current_time = now or unix_now_seconds()

        entity_state = self._state.setdefault(entity_key, {})
        output = dict(values)

        for field in self.allowed_fields:
            value = values.get(field)

            if value is not None:
                entity_state[field] = (value, current_time)
                continue

            previous = entity_state.get(field)

            if previous is None:
                continue

            previous_value, previous_time = previous
            age = current_time - previous_time

            if age <= self.max_age_seconds:
                output[field] = previous_value

        return output


def event_to_dict(event: NormalizedBaseEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")


def validate_normalized_event(event: NormalizedBaseEvent) -> NormalizedBaseEvent:
    """
    Mantido para deixar explícito que schemas normalizados são Pydantic.
    """
    return event