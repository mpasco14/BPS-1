from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sentiment.sentiment_schema import SentimentClassification


class SentimentIndexReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_index"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    asset: str = "BTCUSDT"
    timeframe: str = "5m"

    items_count: int = 0
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0

    weighted_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    sentiment_index: float = Field(default=50.0, ge=0.0, le=100.0)

    social_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    news_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    macro_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)

    panic_score: float = Field(default=0.0, ge=0.0, le=100.0)
    euphoria_score: float = Field(default=0.0, ge=0.0, le=100.0)

    sentiment_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sentiment_momentum: float = Field(default=0.0, ge=-1.0, le=1.0)

    metadata: dict[str, Any] = Field(default_factory=dict)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def score_to_index(score: float) -> float:
    return clamp((score + 1.0) * 50.0, 0.0, 100.0)


def weighted_average(items: list[SentimentClassification]) -> float:
    total_weight = sum(item.weight for item in items)

    if total_weight <= 0:
        return 0.0

    return sum(item.score * item.weight for item in items) / total_weight


def source_group_score(
    items: list[SentimentClassification],
    source_types: set[str],
) -> float:
    selected = [item for item in items if item.source_type in source_types]

    if not selected:
        return 0.0

    return weighted_average(selected)


def macro_score(items: list[SentimentClassification]) -> float:
    selected = [
        item
        for item in items
        if item.event_type in {"macro", "regulatory", "exchange", "funding", "liquidation"}
    ]

    if not selected:
        return 0.0

    return weighted_average(selected)


def build_sentiment_index(
    *,
    items: list[SentimentClassification | dict[str, Any]],
    asset: str = "BTCUSDT",
    timeframe: str = "5m",
    previous_score: float | None = None,
) -> SentimentIndexReport:
    parsed_items = [
        item if isinstance(item, SentimentClassification) else SentimentClassification.model_validate(item)
        for item in items
    ]

    if not parsed_items:
        return SentimentIndexReport(asset=asset, timeframe=timeframe)

    weighted_score = clamp(weighted_average(parsed_items), -1.0, 1.0)
    index = score_to_index(weighted_score)

    bullish_count = sum(1 for item in parsed_items if item.sentiment == "bullish")
    bearish_count = sum(1 for item in parsed_items if item.sentiment == "bearish")
    neutral_count = sum(1 for item in parsed_items if item.sentiment == "neutral")

    social = source_group_score(parsed_items, {"x", "reddit", "manual"})
    news = source_group_score(parsed_items, {"news", "binance"})
    macro = macro_score(parsed_items)

    avg_confidence = sum(item.confidence for item in parsed_items) / len(parsed_items)

    panic_score = clamp(abs(min(weighted_score, 0.0)) * 100.0, 0.0, 100.0)
    euphoria_score = clamp(max(weighted_score, 0.0) * 100.0, 0.0, 100.0)

    momentum = 0.0 if previous_score is None else clamp(weighted_score - previous_score, -1.0, 1.0)

    return SentimentIndexReport(
        asset=asset,
        timeframe=timeframe,
        items_count=len(parsed_items),
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        neutral_count=neutral_count,
        weighted_sentiment_score=round(weighted_score, 8),
        sentiment_index=round(index, 4),
        social_sentiment_score=round(social, 8),
        news_sentiment_score=round(news, 8),
        macro_sentiment_score=round(macro, 8),
        panic_score=round(panic_score, 4),
        euphoria_score=round(euphoria_score, 4),
        sentiment_confidence=round(avg_confidence, 8),
        sentiment_momentum=round(momentum, 8),
        metadata={
            "source_types": sorted(set(item.source_type for item in parsed_items)),
        },
    )