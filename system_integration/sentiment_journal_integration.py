from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


SentimentRegime = Literal["extreme_fear", "fear", "neutral", "greed", "extreme_greed"]
NoTradeDecision = Literal["ALLOW", "BLOCK", "WARN"]


class SentimentJournalConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/system_integration")
    block_extreme_sentiment: bool = True


class SentimentNoTradeInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset: str = "BTCUSDT"
    timeframe: str = "5m"

    sentiment_index: float = 50.0
    fear_greed_value: float = 50.0
    confidence: float = 0.5

    regime: SentimentRegime = "neutral"
    panic_score: float = 0.0
    euphoria_score: float = 0.0

    metadata: dict[str, Any] = Field(default_factory=dict)


class NoTradeEvaluation(BaseModel):
    model_config = ConfigDict(extra="allow")

    decision: NoTradeDecision
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegratedDecisionJournalEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    journal_id: str = Field(default_factory=lambda: f"journal_{uuid4().hex}")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    asset: str
    timeframe: str

    decision: str
    reason: str

    sentiment: dict[str, Any]
    no_trade: dict[str, Any]

    metadata: dict[str, Any] = Field(default_factory=dict)


class SentimentJournalIntegrationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_no_trade_journal_integration"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    approved_for_signal: bool
    status: str

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    sentiment: dict[str, Any]
    no_trade: dict[str, Any]
    journal_entry: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_sentiment_journal_config() -> SentimentJournalConfig:
    return SentimentJournalConfig(
        output_dir=Path(os.getenv("SENTIMENT_JOURNAL_OUTPUT_DIR", "artifacts/system_integration")),
        block_extreme_sentiment=env_bool("SENTIMENT_JOURNAL_BLOCK_EXTREME_SENTIMENT", True),
    )


def evaluate_sentiment_no_trade(
    *,
    sentiment: SentimentNoTradeInput,
    config: SentimentJournalConfig | None = None,
) -> NoTradeEvaluation:
    resolved_config = config or load_sentiment_journal_config()

    blockers: list[str] = []
    warnings: list[str] = []

    if sentiment.confidence < 0.30:
        warnings.append("sentiment_confidence_low")

    if sentiment.regime == "extreme_fear":
        warnings.append("extreme_fear_detected")
        if resolved_config.block_extreme_sentiment:
            blockers.append("extreme_fear_blocks_new_entries")

    if sentiment.regime == "extreme_greed":
        warnings.append("extreme_greed_detected")
        if resolved_config.block_extreme_sentiment:
            blockers.append("extreme_greed_blocks_new_entries")

    if sentiment.panic_score >= 80:
        blockers.append("panic_score_too_high")

    if sentiment.euphoria_score >= 90:
        warnings.append("euphoria_score_high")

    if blockers:
        decision: NoTradeDecision = "BLOCK"
    elif warnings:
        decision = "WARN"
    else:
        decision = "ALLOW"

    return NoTradeEvaluation(
        decision=decision,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "block_extreme_sentiment": resolved_config.block_extreme_sentiment,
        },
    )


def integrate_sentiment_no_trade_journal(
    *,
    sentiment: SentimentNoTradeInput | dict[str, Any],
    no_trade: NoTradeEvaluation | dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> SentimentJournalIntegrationReport:
    parsed_sentiment = sentiment if isinstance(sentiment, SentimentNoTradeInput) else SentimentNoTradeInput.model_validate(sentiment)
    parsed_no_trade = (
        no_trade if isinstance(no_trade, NoTradeEvaluation)
        else NoTradeEvaluation.model_validate(no_trade)
        if no_trade is not None
        else evaluate_sentiment_no_trade(sentiment=parsed_sentiment)
    )

    approved = parsed_no_trade.decision != "BLOCK"

    if approved:
        decision = "SENTIMENT_ACCEPTED"
        reason = "Sentiment and no-trade evaluation allowed signal flow."
    else:
        decision = "SENTIMENT_BLOCKED"
        reason = "Sentiment/no-trade evaluation blocked signal flow."

    journal = IntegratedDecisionJournalEntry(
        asset=parsed_sentiment.asset,
        timeframe=parsed_sentiment.timeframe,
        decision=decision,
        reason=reason,
        sentiment=parsed_sentiment.model_dump(mode="json"),
        no_trade=parsed_no_trade.model_dump(mode="json"),
        metadata=metadata or {},
    )

    return SentimentJournalIntegrationReport(
        approved_for_signal=approved,
        status="PASS" if approved and not parsed_no_trade.warnings else "WARN" if approved else "BLOCKED",
        blockers=parsed_no_trade.blockers,
        warnings=parsed_no_trade.warnings,
        sentiment=parsed_sentiment.model_dump(mode="json"),
        no_trade=parsed_no_trade.model_dump(mode="json"),
        journal_entry=journal.model_dump(mode="json"),
    )


def export_sentiment_journal_integration_report(
    report: SentimentJournalIntegrationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "sentiment_journal_integration_latest",
) -> Path:
    config = load_sentiment_journal_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path