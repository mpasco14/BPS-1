from __future__ import annotations

from typing import Any

from ops.decision_journal import (
    DecisionEvidence,
    DecisionJournalEntry,
    DecisionSource,
    build_decision_journal_entry,
)
from sentiment.sentiment_schema import SentimentFeatureRow
from strategy.sentiment_no_trade_adapter import (
    SentimentNoTradeAssessment,
    evaluate_sentiment_no_trade,
    sentiment_feature_dict,
)


def enrich_decision_evidence_with_sentiment(
    *,
    evidence: DecisionEvidence | dict[str, Any],
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    intended_side: str | None = None,
    apply_sentiment_blockers: bool = True,
) -> DecisionEvidence:
    base = evidence if isinstance(evidence, DecisionEvidence) else DecisionEvidence.model_validate(evidence)
    row = sentiment_row if isinstance(sentiment_row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(sentiment_row)

    assessment = evaluate_sentiment_no_trade(
        sentiment_row=row,
        intended_side=intended_side,
    )

    payload = base.model_dump(mode="json")
    payload.update(
        {
            "sentiment_index": row.btc_sentiment_index,
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
            "sentiment_no_trade_status": assessment.status,
            "sentiment_no_trade_blockers": assessment.blockers,
            "sentiment_no_trade_warnings": assessment.warnings,
            "sentiment_features": sentiment_feature_dict(row),
        }
    )

    if apply_sentiment_blockers and assessment.should_block:
        payload["execution_allowed"] = False
        existing_blockers = list(payload.get("execution_blockers") or [])
        payload["execution_blockers"] = existing_blockers + assessment.blockers

    return DecisionEvidence.model_validate(payload)


def build_decision_journal_entry_with_sentiment(
    *,
    decision_id: str,
    symbol: str,
    side: str | None,
    evidence: DecisionEvidence | dict[str, Any],
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    decision_source: DecisionSource = "system",
    metadata: dict[str, Any] | None = None,
) -> DecisionJournalEntry:
    enriched = enrich_decision_evidence_with_sentiment(
        evidence=evidence,
        sentiment_row=sentiment_row,
        intended_side=side,
        apply_sentiment_blockers=True,
    )

    extra_metadata = dict(metadata or {})
    extra_metadata["sentiment_bridge"] = {
        "enabled": True,
        "sentiment_index": getattr(enriched, "sentiment_index", None),
        "fear_greed_label": getattr(enriched, "fear_greed_label", None),
    }

    return build_decision_journal_entry(
        decision_id=decision_id,
        symbol=symbol,
        side=side,
        evidence=enriched,
        decision_source=decision_source,
        metadata=extra_metadata,
    )