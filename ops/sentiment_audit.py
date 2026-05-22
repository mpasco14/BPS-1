from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from sentiment.sentiment_schema import SentimentClassification, SentimentFeatureRow


load_dotenv()


class SentimentAuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/sentiment")

    min_items: int = 3
    min_confidence: float = 0.40
    min_source_types: int = 1
    max_neutral_ratio: float = 0.80


class SentimentAuditReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_audit"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    symbol: str = "BTCUSDT"
    timeframe: str = "5m"

    items_count: int = 0
    source_types_count: int = 0
    average_confidence: float = 0.0
    neutral_ratio: float = 0.0

    source_distribution: dict[str, int] = Field(default_factory=dict)
    sentiment_distribution: dict[str, int] = Field(default_factory=dict)

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    feature_summary: dict[str, Any] = Field(default_factory=dict)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_sentiment_audit_config() -> SentimentAuditConfig:
    return SentimentAuditConfig(
        output_dir=Path(os.getenv("SENTIMENT_AUDIT_OUTPUT_DIR", "artifacts/sentiment")),
        min_items=env_int("SENTIMENT_AUDIT_MIN_ITEMS", 3),
        min_confidence=env_float("SENTIMENT_AUDIT_MIN_CONFIDENCE", 0.40),
        min_source_types=env_int("SENTIMENT_AUDIT_MIN_SOURCE_TYPES", 1),
        max_neutral_ratio=env_float("SENTIMENT_AUDIT_MAX_NEUTRAL_RATIO", 0.80),
    )


def build_sentiment_audit_report(
    *,
    classifications: list[SentimentClassification | dict[str, Any]],
    feature_row: SentimentFeatureRow | dict[str, Any] | None = None,
    config: SentimentAuditConfig | None = None,
) -> SentimentAuditReport:
    resolved_config = config or load_sentiment_audit_config()

    parsed = [
        item if isinstance(item, SentimentClassification) else SentimentClassification.model_validate(item)
        for item in classifications
    ]

    row = None
    if feature_row is not None:
        row = feature_row if isinstance(feature_row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(feature_row)

    items_count = len(parsed)
    source_distribution = Counter(item.source_type for item in parsed)
    sentiment_distribution = Counter(item.sentiment for item in parsed)

    source_types_count = len(source_distribution)
    avg_confidence = sum(item.confidence for item in parsed) / items_count if items_count else 0.0
    neutral_ratio = sentiment_distribution.get("neutral", 0) / items_count if items_count else 0.0

    blockers: list[str] = []
    warnings: list[str] = []

    if items_count < resolved_config.min_items:
        blockers.append("sentiment_items_below_minimum")

    if source_types_count < resolved_config.min_source_types:
        blockers.append("sentiment_source_diversity_below_minimum")

    if avg_confidence < resolved_config.min_confidence:
        warnings.append("average_sentiment_confidence_below_minimum")

    if neutral_ratio > resolved_config.max_neutral_ratio:
        warnings.append("neutral_ratio_above_limit")

    feature_summary: dict[str, Any] = {}

    if row is not None:
        feature_summary = {
            "btc_sentiment_index": row.btc_sentiment_index,
            "fear_greed_label": row.fear_greed_label,
            "panic_score": row.panic_score,
            "euphoria_score": row.euphoria_score,
            "sentiment_confidence": row.sentiment_confidence,
        }

        if row.sentiment_confidence < resolved_config.min_confidence:
            warnings.append("feature_row_confidence_below_minimum")

    passed = not blockers

    return SentimentAuditReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        symbol=row.symbol if row else "BTCUSDT",
        timeframe=row.timeframe if row else "5m",
        items_count=items_count,
        source_types_count=source_types_count,
        average_confidence=round(avg_confidence, 8),
        neutral_ratio=round(neutral_ratio, 8),
        source_distribution=dict(source_distribution),
        sentiment_distribution=dict(sentiment_distribution),
        blockers=blockers,
        warnings=warnings,
        feature_summary=feature_summary,
    )


def export_sentiment_audit_report(
    report: SentimentAuditReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "sentiment_audit_latest",
) -> Path:
    config = load_sentiment_audit_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path