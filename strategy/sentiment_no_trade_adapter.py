from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from sentiment.sentiment_schema import SentimentFeatureRow
from strategy.no_trade_engine import NoTradeDecision, NoTradeInput, evaluate_no_trade


load_dotenv()


SentimentNoTradeStatus = Literal["PASS", "WARN", "BLOCK"]


class SentimentNoTradeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    min_confidence: float = 0.50
    bullish_index: float = 60.0
    bearish_index: float = 40.0
    extreme_greed_block_long: float = 85.0
    extreme_fear_block_short: float = 15.0
    max_panic_score: float = 90.0
    max_euphoria_score: float = 90.0
    block_conflicting_side: bool = True


class SentimentNoTradeAssessment(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_no_trade_adapter"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: SentimentNoTradeStatus
    should_block: bool

    symbol: str = "BTCUSDT"
    timeframe: str = "5m"
    intended_side: str | None = None

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    sentiment_index: float
    confidence: float
    fear_greed_label: str
    panic_score: float
    euphoria_score: float

    features: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_sentiment_no_trade_config() -> SentimentNoTradeConfig:
    return SentimentNoTradeConfig(
        min_confidence=env_float("SENTIMENT_NO_TRADE_MIN_CONFIDENCE", 0.50),
        bullish_index=env_float("SENTIMENT_NO_TRADE_BULLISH_INDEX", 60),
        bearish_index=env_float("SENTIMENT_NO_TRADE_BEARISH_INDEX", 40),
        extreme_greed_block_long=env_float("SENTIMENT_NO_TRADE_EXTREME_GREED_BLOCK_LONG", 85),
        extreme_fear_block_short=env_float("SENTIMENT_NO_TRADE_EXTREME_FEAR_BLOCK_SHORT", 15),
        max_panic_score=env_float("SENTIMENT_NO_TRADE_MAX_PANIC_SCORE", 90),
        max_euphoria_score=env_float("SENTIMENT_NO_TRADE_MAX_EUPHORIA_SCORE", 90),
        block_conflicting_side=env_bool("SENTIMENT_NO_TRADE_BLOCK_CONFLICTING_SIDE", True),
    )


def sentiment_feature_dict(row: SentimentFeatureRow) -> dict[str, Any]:
    return {
        "btc_sentiment_index": row.btc_sentiment_index,
        "fear_greed_value": row.fear_greed_value,
        "fear_greed_label": row.fear_greed_label,
        "social_sentiment_score": row.social_sentiment_score,
        "news_sentiment_score": row.news_sentiment_score,
        "macro_sentiment_score": row.macro_sentiment_score,
        "panic_score": row.panic_score,
        "euphoria_score": row.euphoria_score,
        "sentiment_momentum": row.sentiment_momentum,
        "sentiment_confidence": row.sentiment_confidence,
        "sentiment_items_count": row.items_count,
        "sentiment_bullish_count": row.bullish_count,
        "sentiment_bearish_count": row.bearish_count,
        "sentiment_neutral_count": row.neutral_count,
    }


def evaluate_sentiment_no_trade(
    *,
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    intended_side: str | None = None,
    config: SentimentNoTradeConfig | None = None,
) -> SentimentNoTradeAssessment:
    row = sentiment_row if isinstance(sentiment_row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(sentiment_row)
    resolved_config = config or load_sentiment_no_trade_config()

    side = (intended_side or "").upper()
    blockers: list[str] = []
    warnings: list[str] = []

    if row.sentiment_confidence < resolved_config.min_confidence:
        warnings.append("sentiment_confidence_below_minimum")

    if row.panic_score >= resolved_config.max_panic_score:
        blockers.append("sentiment_panic_score_above_limit")

    if row.euphoria_score >= resolved_config.max_euphoria_score:
        blockers.append("sentiment_euphoria_score_above_limit")

    if side == "LONG" and row.btc_sentiment_index >= resolved_config.extreme_greed_block_long:
        blockers.append("sentiment_extreme_greed_blocks_long")

    if side == "SHORT" and row.btc_sentiment_index <= resolved_config.extreme_fear_block_short:
        blockers.append("sentiment_extreme_fear_blocks_short")

    if resolved_config.block_conflicting_side:
        if side == "LONG" and row.btc_sentiment_index <= resolved_config.bearish_index:
            blockers.append("sentiment_conflicts_with_long")

        if side == "SHORT" and row.btc_sentiment_index >= resolved_config.bullish_index:
            blockers.append("sentiment_conflicts_with_short")

    if blockers:
        status: SentimentNoTradeStatus = "BLOCK"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    return SentimentNoTradeAssessment(
        status=status,
        should_block=bool(blockers),
        symbol=row.symbol,
        timeframe=row.timeframe,
        intended_side=side or None,
        blockers=blockers,
        warnings=warnings,
        sentiment_index=row.btc_sentiment_index,
        confidence=row.sentiment_confidence,
        fear_greed_label=row.fear_greed_label,
        panic_score=row.panic_score,
        euphoria_score=row.euphoria_score,
        features=sentiment_feature_dict(row),
    )


def build_no_trade_input_with_sentiment(
    *,
    base_input: NoTradeInput | dict[str, Any],
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    intended_side: str | None = None,
) -> NoTradeInput:
    data = base_input if isinstance(base_input, NoTradeInput) else NoTradeInput.model_validate(base_input)
    row = sentiment_row if isinstance(sentiment_row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(sentiment_row)

    payload = data.model_dump(mode="json")
    extra_context = dict(payload.get("extra_context") or {})
    extra_context["sentiment_v2"] = sentiment_feature_dict(row)
    payload["extra_context"] = extra_context

    if intended_side:
        payload["side"] = intended_side

    return NoTradeInput.model_validate(payload)


def evaluate_no_trade_with_sentiment(
    *,
    base_input: NoTradeInput | dict[str, Any],
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    intended_side: str | None = None,
) -> NoTradeDecision:
    enriched_input = build_no_trade_input_with_sentiment(
        base_input=base_input,
        sentiment_row=sentiment_row,
        intended_side=intended_side,
    )

    base_decision = evaluate_no_trade(input_data=enriched_input)

    sentiment_assessment = evaluate_sentiment_no_trade(
        sentiment_row=sentiment_row,
        intended_side=intended_side or enriched_input.side,
    )

    blockers = list(base_decision.blockers) + sentiment_assessment.blockers
    warnings = list(base_decision.warnings) + sentiment_assessment.warnings

    should_trade = not blockers

    input_payload = dict(base_decision.input)
    input_payload["sentiment_no_trade_assessment"] = sentiment_assessment.model_dump(mode="json")

    return NoTradeDecision(
        action="ALLOW_TRADE" if should_trade else "NO_TRADE",
        should_trade=should_trade,
        symbol=base_decision.symbol,
        timeframe=base_decision.timeframe,
        side=base_decision.side,
        blockers=blockers,
        warnings=warnings,
        input=input_payload,
    )