from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from sentiment.fear_greed import FearGreedReport
from sentiment.sentiment_index import SentimentIndexReport
from sentiment.sentiment_schema import SentimentFeatureRow


load_dotenv()


def sentiment_feature_store_path() -> Path:
    return Path(
        os.getenv(
            "SENTIMENT_FEATURE_STORE_FILE",
            "artifacts/sentiment/sentiment_features.jsonl",
        )
    )


def build_sentiment_feature_row(
    *,
    sentiment_index: SentimentIndexReport | dict[str, Any],
    fear_greed: FearGreedReport | dict[str, Any],
    symbol: str = "BTCUSDT",
    timeframe: str = "5m",
) -> SentimentFeatureRow:
    index = (
        sentiment_index
        if isinstance(sentiment_index, SentimentIndexReport)
        else SentimentIndexReport.model_validate(sentiment_index)
    )
    fg = fear_greed if isinstance(fear_greed, FearGreedReport) else FearGreedReport.model_validate(fear_greed)

    return SentimentFeatureRow(
        timestamp=index.generated_at,
        symbol=symbol,
        timeframe=timeframe,
        btc_sentiment_index=index.sentiment_index,
        fear_greed_value=fg.value,
        fear_greed_label=fg.label,
        social_sentiment_score=index.social_sentiment_score,
        news_sentiment_score=index.news_sentiment_score,
        macro_sentiment_score=index.macro_sentiment_score,
        panic_score=index.panic_score,
        euphoria_score=index.euphoria_score,
        sentiment_momentum=index.sentiment_momentum,
        sentiment_confidence=index.sentiment_confidence,
        items_count=index.items_count,
        bullish_count=index.bullish_count,
        bearish_count=index.bearish_count,
        neutral_count=index.neutral_count,
        metadata={
            "weighted_sentiment_score": index.weighted_sentiment_score,
            "source_types": index.metadata.get("source_types", []),
        },
    )


def append_sentiment_feature_row(
    row: SentimentFeatureRow,
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or sentiment_feature_store_path())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def export_sentiment_feature_rows(
    rows: list[SentimentFeatureRow],
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or sentiment_feature_store_path())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def load_sentiment_feature_rows(
    path: str | Path | None = None,
) -> list[SentimentFeatureRow]:
    input_path = Path(path or sentiment_feature_store_path())

    if not input_path.exists():
        return []

    rows: list[SentimentFeatureRow] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            rows.append(SentimentFeatureRow.model_validate(json.loads(line)))

    return rows