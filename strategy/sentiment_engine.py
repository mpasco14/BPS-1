"""
Binance Futures sentiment strategy engine.

Responsabilidades:
- Converter eventos de sentimento em sinais estratégicos por timeframe.
- Aplicar pesos menores em 5m/15m e maiores em 1h/1d.
- Usar volume_mentions como amplificador de força, não de direção.
- Aplicar média móvel de 30 minutos para reduzir ruído.
- Gerar sentiment_score final em [-1, +1].

Este módulo NÃO coleta notícias.
Este módulo NÃO executa ordens.
Este módulo NÃO substitui o risk manager.
"""

from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


Timeframe = Literal["5m", "15m", "1h", "1d"]

SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "1d"}


DEFAULT_TIMEFRAME_WEIGHTS = {
    "5m": 0.03,
    "15m": 0.05,
    "1h": 0.10,
    "1d": 0.20,
}


class SentimentEvent(BaseModel):
    """
    Evento de sentimento normalizado para uso estratégico.
    """

    model_config = ConfigDict(extra="allow")

    source: str = "sentiment"
    provider: str = "unknown"
    event_type: str = "sentiment_snapshot"

    asset: str = "BTC"
    category: str = "social_news_sentiment"
    interval: str = "snapshot"

    timestamp: int | None = None
    collected_at: str | None = None

    sentiment_score: float
    volume_mentions: int = 0

    keywords: list[str] = Field(default_factory=list)
    positive_hits: list[str] = Field(default_factory=list)
    negative_hits: list[str] = Field(default_factory=list)
    neutral_hits: list[str] = Field(default_factory=list)

    articles: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("asset")
    @classmethod
    def normalize_asset(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("asset não pode ser vazio")

        return value

    @field_validator("sentiment_score")
    @classmethod
    def validate_sentiment_score(cls, value: float) -> float:
        if value < -1 or value > 1:
            raise ValueError("sentiment_score deve estar entre -1 e +1")

        return float(value)

    @field_validator("volume_mentions")
    @classmethod
    def validate_volume_mentions(cls, value: int) -> int:
        if value < 0:
            raise ValueError("volume_mentions não pode ser negativo")

        return int(value)


class SentimentSnapshot(BaseModel):
    """
    Resultado agregado da análise de sentimento para um timeframe.
    """

    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_engine"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: Timeframe

    raw_sentiment_score: float
    moving_average_score: float
    mention_amplifier: float
    timeframe_weight: float
    sentiment_score: float

    volume_mentions: int
    event_count: int

    keywords: list[str] = Field(default_factory=list)
    positive_hits: list[str] = Field(default_factory=list)
    negative_hits: list[str] = Field(default_factory=list)
    neutral_hits: list[str] = Field(default_factory=list)

    risk_keyword_hits: list[str] = Field(default_factory=list)
    bullish_keyword_hits: list[str] = Field(default_factory=list)

    is_ready: bool

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("symbol não pode ser vazio")

        return value

    @field_validator("raw_sentiment_score", "moving_average_score", "sentiment_score")
    @classmethod
    def validate_scores(cls, value: float) -> float:
        if value < -1 or value > 1:
            raise ValueError("score deve estar entre -1 e +1")

        return float(value)


def normalize_timeframe(timeframe: str) -> Timeframe:
    mapping = {
        "5M": "5m",
        "5m": "5m",
        "15M": "15m",
        "15m": "15m",
        "1H": "1h",
        "1h": "1h",
        "1D": "1d",
        "1d": "1d",
    }

    normalized = mapping.get(timeframe.strip())

    if normalized not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"timeframe não suportado: {timeframe}")

    return normalized  # type: ignore[return-value]


def clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []

    return [item.strip() for item in value.split(",") if item.strip()]


def env_float(name: str, default: float) -> float:
    value = safe_float(os.getenv(name))

    if value is None:
        return default

    return value


def unix_now_seconds() -> int:
    return int(time.time())


def parse_timestamp_seconds(value: Any) -> int | None:
    """
    Aceita:
    - Unix seconds
    - Unix milliseconds
    - ISO string
    - None
    """
    if value is None:
        return None

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
            return parse_timestamp_seconds(int(stripped))

        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return int(parsed.astimezone(timezone.utc).timestamp())
        except ValueError:
            return None

    return None


def get_event_timestamp(event: SentimentEvent) -> int | None:
    timestamp = parse_timestamp_seconds(event.timestamp)

    if timestamp is not None:
        return timestamp

    return parse_timestamp_seconds(event.collected_at)


def get_timeframe_weight(timeframe: str) -> float:
    tf = normalize_timeframe(timeframe)

    env_names = {
        "5m": "SENTIMENT_WEIGHT_5M",
        "15m": "SENTIMENT_WEIGHT_15M",
        "1h": "SENTIMENT_WEIGHT_1H",
        "1d": "SENTIMENT_WEIGHT_1D",
    }

    return clamp(
        env_float(env_names[tf], DEFAULT_TIMEFRAME_WEIGHTS[tf]),
        lower=0.0,
        upper=1.0,
    )


def normalize_sentiment_event(raw: dict[str, Any]) -> SentimentEvent:
    return SentimentEvent(
        source=str(raw.get("source") or "sentiment"),
        provider=str(raw.get("provider") or "unknown"),
        event_type=str(raw.get("event_type") or "sentiment_snapshot"),
        asset=str(raw.get("asset") or "BTC"),
        category=str(raw.get("category") or "social_news_sentiment"),
        interval=str(raw.get("interval") or "snapshot"),
        timestamp=raw.get("timestamp"),
        collected_at=raw.get("collected_at"),
        sentiment_score=float(raw.get("sentiment_score")),
        volume_mentions=int(raw.get("volume_mentions") or 0),
        keywords=list(raw.get("keywords") or []),
        positive_hits=list(raw.get("positive_hits") or []),
        negative_hits=list(raw.get("negative_hits") or []),
        neutral_hits=list(raw.get("neutral_hits") or []),
        articles=list(raw.get("articles") or []),
        raw=raw,
    )


def filter_events_by_window(
    events: list[SentimentEvent],
    *,
    window_minutes: int,
    now_ts: int | None = None,
) -> list[SentimentEvent]:
    if not events:
        return []

    current_ts = now_ts or unix_now_seconds()
    min_ts = current_ts - window_minutes * 60

    filtered: list[SentimentEvent] = []

    for event in events:
        event_ts = get_event_timestamp(event)

        if event_ts is None:
            filtered.append(event)
            continue

        if event_ts >= min_ts:
            filtered.append(event)

    return filtered


def calculate_moving_average_score(events: list[SentimentEvent]) -> float:
    if not events:
        return 0.0

    total = sum(event.sentiment_score for event in events)

    return clamp(total / len(events))


def calculate_volume_mentions(events: list[SentimentEvent]) -> int:
    return sum(event.volume_mentions for event in events)


def calculate_mention_amplifier(
    volume_mentions: int,
    *,
    baseline: float | None = None,
    max_amplifier: float | None = None,
) -> float:
    """
    Volume de menções amplifica força, não direção.

    Exemplo:
    score = -0.30 com spike de menções continua negativo,
    apenas mais forte.
    """
    baseline_value = baseline if baseline is not None else env_float("SENTIMENT_VOLUME_BASELINE", 10.0)
    max_amp = max_amplifier if max_amplifier is not None else env_float("SENTIMENT_MAX_VOLUME_AMPLIFIER", 1.50)

    if volume_mentions <= 0 or baseline_value <= 0:
        return 1.0

    ratio = math.log1p(volume_mentions) / math.log1p(baseline_value)
    ratio = min(max(ratio, 0.0), 1.0)

    return max(1.0, min(max_amp, 1.0 + ratio * (max_amp - 1.0)))


def unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values), key=lambda item: item.lower())


def collect_keywords(events: list[SentimentEvent], attr: str) -> list[str]:
    collected: list[str] = []

    for event in events:
        values = getattr(event, attr, [])

        if isinstance(values, list):
            collected.extend(str(item) for item in values)

    return unique_sorted(collected)


def keyword_hits_from_config(keywords: list[str], env_name: str) -> list[str]:
    configured = parse_csv_env(os.getenv(env_name))

    configured_lower = {item.lower() for item in configured}
    hits = [keyword for keyword in keywords if keyword.lower() in configured_lower]

    return unique_sorted(hits)


def calculate_sentiment_snapshot(
    *,
    timeframe: str,
    events: list[dict[str, Any]] | list[SentimentEvent],
    symbol: str = "BTCUSDT",
    now_ts: int | None = None,
) -> SentimentSnapshot:
    tf = normalize_timeframe(timeframe)

    normalized_events = [
        event if isinstance(event, SentimentEvent) else normalize_sentiment_event(event)
        for event in events
    ]

    window_minutes = int(os.getenv("SENTIMENT_MOVING_AVERAGE_WINDOW_MINUTES", "30"))

    recent_events = filter_events_by_window(
        normalized_events,
        window_minutes=window_minutes,
        now_ts=now_ts,
    )

    moving_average = calculate_moving_average_score(recent_events)
    volume_mentions = calculate_volume_mentions(recent_events)
    amplifier = calculate_mention_amplifier(volume_mentions)

    amplified_score = clamp(moving_average * amplifier)
    timeframe_weight = get_timeframe_weight(tf)
    final_score = clamp(amplified_score * timeframe_weight)

    keywords = collect_keywords(recent_events, "keywords")
    positive_hits = collect_keywords(recent_events, "positive_hits")
    negative_hits = collect_keywords(recent_events, "negative_hits")
    neutral_hits = collect_keywords(recent_events, "neutral_hits")

    risk_hits = keyword_hits_from_config(
        unique_sorted(keywords + negative_hits),
        "SENTIMENT_RISK_KEYWORDS",
    )

    bullish_hits = keyword_hits_from_config(
        unique_sorted(keywords + positive_hits),
        "SENTIMENT_BULLISH_KEYWORDS",
    )

    return SentimentSnapshot(
        symbol=symbol,
        timeframe=tf,
        raw_sentiment_score=moving_average,
        moving_average_score=moving_average,
        mention_amplifier=amplifier,
        timeframe_weight=timeframe_weight,
        sentiment_score=final_score,
        volume_mentions=volume_mentions,
        event_count=len(recent_events),
        keywords=keywords,
        positive_hits=positive_hits,
        negative_hits=negative_hits,
        neutral_hits=neutral_hits,
        risk_keyword_hits=risk_hits,
        bullish_keyword_hits=bullish_hits,
        is_ready=len(recent_events) > 0,
    )


def calculate_many_timeframes(
    events: list[dict[str, Any]] | list[SentimentEvent],
    *,
    symbol: str = "BTCUSDT",
    timeframes: list[str] | None = None,
    now_ts: int | None = None,
) -> dict[str, SentimentSnapshot]:
    selected_timeframes = timeframes or ["5m", "15m", "1h", "1d"]

    snapshots: dict[str, SentimentSnapshot] = {}

    for timeframe in selected_timeframes:
        tf = normalize_timeframe(timeframe)

        snapshots[tf] = calculate_sentiment_snapshot(
            timeframe=tf,
            events=events,
            symbol=symbol,
            now_ts=now_ts,
        )

    return snapshots


def snapshot_to_dict(snapshot: SentimentSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(mode="json")