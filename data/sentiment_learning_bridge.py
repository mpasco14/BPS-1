from __future__ import annotations

from typing import Any

from data.learning_feedback_dataset import (
    LearningFeedbackRow,
    build_learning_feedback_row,
)
from ops.decision_journal import DecisionJournalEntry
from ops.outcome_attribution import OutcomeAttributionReport
from sentiment.sentiment_schema import SentimentFeatureRow
from strategy.sentiment_no_trade_adapter import evaluate_sentiment_no_trade, sentiment_feature_dict


def enrich_learning_feedback_row_with_sentiment(
    *,
    row: LearningFeedbackRow | dict[str, Any],
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    intended_side: str | None = None,
) -> LearningFeedbackRow:
    base = row if isinstance(row, LearningFeedbackRow) else LearningFeedbackRow.model_validate(row)
    sentiment = sentiment_row if isinstance(sentiment_row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(sentiment_row)

    assessment = evaluate_sentiment_no_trade(
        sentiment_row=sentiment,
        intended_side=intended_side or base.side,
    )

    features = dict(base.features or {})
    features.update(sentiment_feature_dict(sentiment))
    features["sentiment_no_trade_status"] = assessment.status
    features["sentiment_no_trade_blockers"] = assessment.blockers

    metadata = dict(base.metadata or {})
    metadata["sentiment_v2"] = {
        "enabled": True,
        "assessment": assessment.model_dump(mode="json"),
    }

    return base.model_copy(
        update={
            "features": features,
            "metadata": metadata,
        }
    )


def build_sentiment_learning_feedback_row(
    *,
    decision: DecisionJournalEntry | dict[str, Any],
    sentiment_row: SentimentFeatureRow | dict[str, Any],
    outcome: OutcomeAttributionReport | dict[str, Any] | None = None,
    intended_side: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> LearningFeedbackRow:
    row = build_learning_feedback_row(
        decision=decision,
        outcome=outcome,
        metadata=metadata,
    )

    return enrich_learning_feedback_row_with_sentiment(
        row=row,
        sentiment_row=sentiment_row,
        intended_side=intended_side or row.side,
    )