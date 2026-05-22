from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from sentiment.sentiment_schema import SentimentFeatureRow


load_dotenv()


SentimentSignalAction = Literal[
    "NEUTRAL",
    "BOOST_LONG",
    "BOOST_SHORT",
    "REDUCE_CONFIDENCE",
    "BLOCK_LONG",
    "BLOCK_SHORT",
]


class SentimentIntegrationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    min_confidence: float = 0.50
    bullish_index: float = 60.0
    bearish_index: float = 40.0
    extreme_greed_block_long: float = 85.0
    extreme_fear_block_short: float = 15.0


class SentimentSignalContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_feature_integration"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    symbol: str = "BTCUSDT"
    timeframe: str = "5m"

    action: SentimentSignalAction = "NEUTRAL"
    sentiment_score: float = 0.0
    sentiment_index: float = 50.0
    confidence: float = 0.0

    should_block: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    features: dict[str, Any] = Field(default_factory=dict)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_sentiment_integration_config() -> SentimentIntegrationConfig:
    return SentimentIntegrationConfig(
        min_confidence=env_float("SENTIMENT_INTEGRATION_MIN_CONFIDENCE", 0.50),
        bullish_index=env_float("SENTIMENT_INTEGRATION_BULLISH_INDEX", 60),
        bearish_index=env_float("SENTIMENT_INTEGRATION_BEARISH_INDEX", 40),
        extreme_greed_block_long=env_float("SENTIMENT_INTEGRATION_EXTREME_GREED_BLOCK_LONG", 85),
        extreme_fear_block_short=env_float("SENTIMENT_INTEGRATION_EXTREME_FEAR_BLOCK_SHORT", 15),
    )


def sentiment_row_to_feature_dict(row: SentimentFeatureRow | dict[str, Any]) -> dict[str, Any]:
    parsed = row if isinstance(row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(row)

    return {
        "btc_sentiment_index": parsed.btc_sentiment_index,
        "fear_greed_value": parsed.fear_greed_value,
        "fear_greed_label": parsed.fear_greed_label,
        "social_sentiment_score": parsed.social_sentiment_score,
        "news_sentiment_score": parsed.news_sentiment_score,
        "macro_sentiment_score": parsed.macro_sentiment_score,
        "panic_score": parsed.panic_score,
        "euphoria_score": parsed.euphoria_score,
        "sentiment_momentum": parsed.sentiment_momentum,
        "sentiment_confidence": parsed.sentiment_confidence,
        "sentiment_items_count": parsed.items_count,
        "sentiment_bullish_count": parsed.bullish_count,
        "sentiment_bearish_count": parsed.bearish_count,
        "sentiment_neutral_count": parsed.neutral_count,
    }


def merge_sentiment_features(
    *,
    base_features: dict[str, Any],
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    namespace: str = "sentiment_v2",
) -> dict[str, Any]:
    sentiment_features = sentiment_row_to_feature_dict(sentiment_row)

    merged = dict(base_features)
    merged.update(sentiment_features)
    merged[namespace] = sentiment_features

    return merged


def evaluate_sentiment_signal_context(
    *,
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    side: str | None = None,
    config: SentimentIntegrationConfig | None = None,
) -> SentimentSignalContext:
    resolved_config = config or load_sentiment_integration_config()
    row = sentiment_row if isinstance(sentiment_row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(sentiment_row)

    blockers: list[str] = []
    warnings: list[str] = []

    side_upper = (side or "").upper()
    sentiment_index = row.btc_sentiment_index
    confidence = row.sentiment_confidence
    sentiment_score = (sentiment_index - 50.0) / 50.0

    action: SentimentSignalAction = "NEUTRAL"

    if confidence < resolved_config.min_confidence:
        warnings.append("sentiment_confidence_below_minimum")
        action = "REDUCE_CONFIDENCE"

    if sentiment_index >= resolved_config.extreme_greed_block_long and side_upper == "LONG":
        blockers.append("extreme_greed_blocks_late_long")
        action = "BLOCK_LONG"

    elif sentiment_index <= resolved_config.extreme_fear_block_short and side_upper == "SHORT":
        blockers.append("extreme_fear_blocks_late_short")
        action = "BLOCK_SHORT"

    elif sentiment_index >= resolved_config.bullish_index:
        action = "BOOST_LONG"

    elif sentiment_index <= resolved_config.bearish_index:
        action = "BOOST_SHORT"

    return SentimentSignalContext(
        symbol=row.symbol,
        timeframe=row.timeframe,
        action=action,
        sentiment_score=round(sentiment_score, 8),
        sentiment_index=sentiment_index,
        confidence=confidence,
        should_block=bool(blockers),
        blockers=blockers,
        warnings=warnings,
        features=sentiment_row_to_feature_dict(row),
    )


def build_signal_engine_payload_with_sentiment(
    *,
    base_features: dict[str, Any],
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    side: str | None = None,
) -> dict[str, Any]:
    merged = merge_sentiment_features(
        base_features=base_features,
        sentiment_row=sentiment_row,
    )

    context = evaluate_sentiment_signal_context(
        sentiment_row=sentiment_row,
        side=side,
    )

    merged["sentiment_signal_context"] = context.model_dump(mode="json")
    merged["sentiment_blockers"] = context.blockers
    merged["sentiment_warnings"] = context.warnings
    merged["sentiment_should_block"] = context.should_block

    return merged