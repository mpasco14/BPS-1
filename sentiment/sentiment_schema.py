from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SentimentSourceType = Literal["x", "reddit", "news", "binance", "manual", "other"]
SentimentLabel = Literal["bullish", "bearish", "neutral"]
SentimentUrgency = Literal["low", "medium", "high"]
SentimentTimeHorizon = Literal["5m", "15m", "1h", "1D", "unknown"]
SentimentEventType = Literal[
    "market",
    "macro",
    "exchange",
    "regulatory",
    "liquidation",
    "funding",
    "technical",
    "social",
    "unknown",
]


class RawSentimentItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    item_id: str
    source_type: SentimentSourceType = "other"
    source_name: str = "unknown"

    text: str
    url: str | None = None
    author: str | None = None

    language: str | None = None
    asset: str | None = None
    symbols: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    metadata: dict[str, Any] = Field(default_factory=dict)


class CleanSentimentItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    item_id: str
    source_type: SentimentSourceType
    source_name: str

    original_text: str
    clean_text: str
    text_hash: str

    language: str
    asset: str
    symbols: list[str] = Field(default_factory=list)

    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    is_relevant: bool = False
    is_duplicate: bool = False

    created_at: datetime
    collected_at: datetime
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    metadata: dict[str, Any] = Field(default_factory=dict)


class SentimentClassification(BaseModel):
    model_config = ConfigDict(extra="allow")

    item_id: str
    source_type: SentimentSourceType
    source_name: str

    asset: str = "BTCUSDT"
    symbols: list[str] = Field(default_factory=list)

    sentiment: SentimentLabel = "neutral"
    score: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    event_type: SentimentEventType = "unknown"
    urgency: SentimentUrgency = "low"
    time_horizon: SentimentTimeHorizon = "unknown"

    weight: float = 1.0
    weighted_score: float = 0.0

    text_hash: str | None = None
    reason: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    metadata: dict[str, Any] = Field(default_factory=dict)


class SentimentFeatureRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_feature_store"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"

    btc_sentiment_index: float = Field(default=50.0, ge=0.0, le=100.0)
    fear_greed_value: float = Field(default=50.0, ge=0.0, le=100.0)
    fear_greed_label: str = "neutral"

    social_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    news_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    macro_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)

    panic_score: float = Field(default=0.0, ge=0.0, le=100.0)
    euphoria_score: float = Field(default=0.0, ge=0.0, le=100.0)

    sentiment_momentum: float = Field(default=0.0, ge=-1.0, le=1.0)
    sentiment_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    items_count: int = 0
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0

    metadata: dict[str, Any] = Field(default_factory=dict)