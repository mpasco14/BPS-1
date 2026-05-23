from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ops.sentiment_audit import SentimentAuditReport
from ops.strategy_health import (
    StrategyHealthInput,
    StrategyHealthReport,
    build_strategy_health_report,
)
from sentiment.sentiment_schema import SentimentFeatureRow


load_dotenv()


SentimentStrategyHealthStatus = Literal["HEALTHY", "WATCH", "BLOCKED"]


class SentimentStrategyHealthConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    min_score: float = 0.70
    blocking_score: float = 0.50
    min_items: int = 3
    min_confidence: float = 0.40
    max_neutral_ratio: float = 0.80


class SentimentStrategyHealthReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_strategy_health"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: SentimentStrategyHealthStatus
    passed: bool

    base_health_score: float
    sentiment_health_score: float
    combined_health_score: float

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    base_strategy_health: dict[str, Any]
    sentiment_summary: dict[str, Any] = Field(default_factory=dict)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_sentiment_strategy_health_config() -> SentimentStrategyHealthConfig:
    return SentimentStrategyHealthConfig(
        min_score=env_float("SENTIMENT_STRATEGY_HEALTH_MIN_SCORE", 0.70),
        blocking_score=env_float("SENTIMENT_STRATEGY_HEALTH_BLOCKING_SCORE", 0.50),
        min_items=env_int("SENTIMENT_STRATEGY_HEALTH_MIN_ITEMS", 3),
        min_confidence=env_float("SENTIMENT_STRATEGY_HEALTH_MIN_CONFIDENCE", 0.40),
        max_neutral_ratio=env_float("SENTIMENT_STRATEGY_HEALTH_MAX_NEUTRAL_RATIO", 0.80),
    )


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def calculate_sentiment_health_score(
    *,
    sentiment_row: SentimentFeatureRow,
    audit_report: SentimentAuditReport | None,
    config: SentimentStrategyHealthConfig,
) -> float:
    items_score = clamp(sentiment_row.items_count / max(config.min_items, 1))
    confidence_score = clamp(sentiment_row.sentiment_confidence / max(config.min_confidence, 0.01))

    if audit_report is None:
        audit_score = 0.75
        neutral_score = 1.0
    else:
        audit_score = 1.0 if audit_report.passed else 0.25
        neutral_score = clamp(1.0 - (audit_report.neutral_ratio / max(config.max_neutral_ratio, 0.01)))

    score = (
        items_score * 0.25
        + confidence_score * 0.35
        + audit_score * 0.25
        + neutral_score * 0.15
    )

    return round(clamp(score), 6)


def build_sentiment_strategy_health_report(
    *,
    strategy_input: StrategyHealthInput | dict[str, Any],
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    audit_report: SentimentAuditReport | dict[str, Any] | None = None,
    config: SentimentStrategyHealthConfig | None = None,
) -> SentimentStrategyHealthReport:
    resolved_config = config or load_sentiment_strategy_health_config()

    base_input = strategy_input if isinstance(strategy_input, StrategyHealthInput) else StrategyHealthInput.model_validate(strategy_input)
    sentiment = sentiment_row if isinstance(sentiment_row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(sentiment_row)

    audit = None
    if audit_report is not None:
        audit = audit_report if isinstance(audit_report, SentimentAuditReport) else SentimentAuditReport.model_validate(audit_report)

    base_report = build_strategy_health_report(input_data=base_input)

    sentiment_score = calculate_sentiment_health_score(
        sentiment_row=sentiment,
        audit_report=audit,
        config=resolved_config,
    )

    combined_score = round((base_report.health_score * 0.75) + (sentiment_score * 0.25), 6)

    blockers = list(base_report.blockers)
    warnings = list(base_report.warnings)

    if audit is not None and not audit.passed:
        blockers.extend(audit.blockers)

    if sentiment.items_count < resolved_config.min_items:
        blockers.append("sentiment_items_below_health_minimum")

    if sentiment.sentiment_confidence < resolved_config.min_confidence:
        warnings.append("sentiment_confidence_below_health_minimum")

    if combined_score < resolved_config.blocking_score:
        blockers.append("combined_sentiment_strategy_health_below_blocking_score")
    elif combined_score < resolved_config.min_score:
        warnings.append("combined_sentiment_strategy_health_below_min_score")

    passed = not blockers and combined_score >= resolved_config.min_score

    if blockers:
        status: SentimentStrategyHealthStatus = "BLOCKED"
    elif warnings:
        status = "WATCH"
    else:
        status = "HEALTHY"

    return SentimentStrategyHealthReport(
        status=status,
        passed=passed,
        base_health_score=base_report.health_score,
        sentiment_health_score=sentiment_score,
        combined_health_score=combined_score,
        blockers=blockers,
        warnings=warnings,
        base_strategy_health=base_report.model_dump(mode="json"),
        sentiment_summary={
            "btc_sentiment_index": sentiment.btc_sentiment_index,
            "fear_greed_label": sentiment.fear_greed_label,
            "sentiment_confidence": sentiment.sentiment_confidence,
            "items_count": sentiment.items_count,
            "panic_score": sentiment.panic_score,
            "euphoria_score": sentiment.euphoria_score,
            "audit_status": audit.status if audit else None,
        },
    )


def export_sentiment_strategy_health_report(
    report: SentimentStrategyHealthReport,
    *,
    output_dir: str | Path = "artifacts/sentiment",
    name: str = "sentiment_strategy_health_latest",
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path