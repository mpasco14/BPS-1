from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from sentiment.sentiment_schema import SentimentClassification


load_dotenv()


class SourceWeightConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    time_decay_halflife_minutes: float = 60.0

    source_type_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "x": 0.75,
            "reddit": 0.60,
            "news": 1.00,
            "binance": 1.00,
            "manual": 0.50,
            "other": 0.40,
        }
    )

    source_name_overrides: dict[str, float] = Field(default_factory=dict)

    tier1_news_weight: float = 1.25
    tier2_news_weight: float = 1.00
    anonymous_social_weight: float = 0.60


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_source_weight_config() -> SourceWeightConfig:
    return SourceWeightConfig(
        time_decay_halflife_minutes=env_float("SENTIMENT_TIME_DECAY_HALFLIFE_MINUTES", 60),
        source_type_weights={
            "x": env_float("SENTIMENT_WEIGHT_X", 0.75),
            "reddit": env_float("SENTIMENT_WEIGHT_REDDIT", 0.60),
            "news": env_float("SENTIMENT_WEIGHT_NEWS", 1.00),
            "binance": env_float("SENTIMENT_WEIGHT_BINANCE", 1.00),
            "manual": env_float("SENTIMENT_WEIGHT_MANUAL", 0.50),
            "other": env_float("SENTIMENT_WEIGHT_OTHER", 0.40),
        },
        tier1_news_weight=env_float("SENTIMENT_TIER1_NEWS_WEIGHT", 1.25),
        tier2_news_weight=env_float("SENTIMENT_TIER2_NEWS_WEIGHT", 1.00),
        anonymous_social_weight=env_float("SENTIMENT_ANONYMOUS_SOCIAL_WEIGHT", 0.60),
    )


def minutes_old(created_at: datetime, *, now: datetime | None = None) -> float:
    resolved_now = now or datetime.now(timezone.utc)

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)

    return max(0.0, (resolved_now - created_at).total_seconds() / 60)


def time_decay_weight(
    created_at: datetime,
    *,
    now: datetime | None = None,
    halflife_minutes: float = 60.0,
) -> float:
    if halflife_minutes <= 0:
        return 1.0

    age = minutes_old(created_at, now=now)

    return math.pow(0.5, age / halflife_minutes)


def calculate_source_weight(
    item: SentimentClassification,
    *,
    config: SourceWeightConfig | None = None,
    now: datetime | None = None,
) -> float:
    resolved_config = config or load_source_weight_config()

    base = resolved_config.source_type_weights.get(item.source_type, 0.40)
    source_override = resolved_config.source_name_overrides.get(item.source_name.lower())

    if source_override is not None:
        base = source_override

    tier = str(item.metadata.get("source_tier", "")).lower()

    if item.source_type == "news" and tier == "tier1":
        base *= resolved_config.tier1_news_weight
    elif item.source_type == "news" and tier == "tier2":
        base *= resolved_config.tier2_news_weight

    if item.source_type in {"x", "reddit"} and not item.metadata.get("verified_author", False):
        base *= resolved_config.anonymous_social_weight

    decay = time_decay_weight(
        item.created_at,
        now=now,
        halflife_minutes=resolved_config.time_decay_halflife_minutes,
    )

    return round(max(0.0, min(2.0, base * decay * item.confidence)), 8)


def apply_source_weights(
    items: list[SentimentClassification | dict[str, Any]],
    *,
    config: SourceWeightConfig | None = None,
    now: datetime | None = None,
) -> list[SentimentClassification]:
    weighted_items: list[SentimentClassification] = []

    for item in items:
        parsed = item if isinstance(item, SentimentClassification) else SentimentClassification.model_validate(item)

        weight = calculate_source_weight(parsed, config=config, now=now)

        weighted_items.append(
            parsed.model_copy(
                update={
                    "weight": weight,
                    "weighted_score": parsed.score * weight,
                }
            )
        )

    return weighted_items