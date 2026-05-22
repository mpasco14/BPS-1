from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from sentiment.sentiment_index import SentimentIndexReport


load_dotenv()


FearGreedLabel = Literal[
    "extreme_fear",
    "fear",
    "neutral",
    "greed",
    "extreme_greed",
]


class FearGreedReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "fear_greed"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    asset: str = "BTCUSDT"
    timeframe: str = "5m"

    value: float = Field(default=50.0, ge=0.0, le=100.0)
    label: FearGreedLabel = "neutral"

    interpretation: str
    panic_score: float = 0.0
    euphoria_score: float = 0.0

    metadata: dict[str, Any] = Field(default_factory=dict)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def classify_fear_greed(value: float) -> FearGreedLabel:
    extreme_fear_max = env_float("SENTIMENT_FEAR_GREED_EXTREME_FEAR_MAX", 20)
    fear_max = env_float("SENTIMENT_FEAR_GREED_FEAR_MAX", 40)
    neutral_max = env_float("SENTIMENT_FEAR_GREED_NEUTRAL_MAX", 60)
    greed_max = env_float("SENTIMENT_FEAR_GREED_GREED_MAX", 80)

    if value <= extreme_fear_max:
        return "extreme_fear"

    if value <= fear_max:
        return "fear"

    if value <= neutral_max:
        return "neutral"

    if value <= greed_max:
        return "greed"

    return "extreme_greed"


def interpretation_for_label(label: FearGreedLabel) -> str:
    return {
        "extreme_fear": "Medo extremo; risco de pânico e reversões violentas.",
        "fear": "Medo; mercado defensivo e sensível a notícias negativas.",
        "neutral": "Neutro; sentimento sem pressão direcional dominante.",
        "greed": "Ganância; sentimento positivo, mas atenção a entradas tardias.",
        "extreme_greed": "Ganância extrema; risco de euforia, FOMO e reversão.",
    }[label]


def build_fear_greed_report(
    *,
    sentiment_index: SentimentIndexReport | dict[str, Any],
) -> FearGreedReport:
    index = (
        sentiment_index
        if isinstance(sentiment_index, SentimentIndexReport)
        else SentimentIndexReport.model_validate(sentiment_index)
    )

    label = classify_fear_greed(index.sentiment_index)

    return FearGreedReport(
        asset=index.asset,
        timeframe=index.timeframe,
        value=index.sentiment_index,
        label=label,
        interpretation=interpretation_for_label(label),
        panic_score=index.panic_score,
        euphoria_score=index.euphoria_score,
        metadata={
            "weighted_sentiment_score": index.weighted_sentiment_score,
            "items_count": index.items_count,
            "sentiment_confidence": index.sentiment_confidence,
        },
    )