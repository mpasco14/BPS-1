from data.sentiment_learning_bridge import (
    build_sentiment_learning_feedback_row,
    enrich_learning_feedback_row_with_sentiment,
)
from data.learning_feedback_dataset import LearningFeedbackRow
from ops.decision_journal import DecisionEvidence, build_decision_journal_entry
from sentiment.sentiment_schema import SentimentFeatureRow


def sample_row():
    return SentimentFeatureRow(
        btc_sentiment_index=70,
        fear_greed_value=70,
        fear_greed_label="greed",
        sentiment_confidence=0.8,
        items_count=5,
    )


def test_enrich_learning_feedback_row_with_sentiment():
    row = LearningFeedbackRow(
        decision_id="decision_1",
        final_decision="ENTER",
        features={},
    )

    enriched = enrich_learning_feedback_row_with_sentiment(
        row=row,
        sentiment_row=sample_row(),
        intended_side="LONG",
    )

    assert enriched.features["btc_sentiment_index"] == 70
    assert "sentiment_v2" in enriched.metadata


def test_build_sentiment_learning_feedback_row():
    decision = build_decision_journal_entry(
        decision_id="decision_2",
        symbol="BTCUSDT",
        side="LONG",
        evidence=DecisionEvidence(expected_value_usd=0.5),
    )

    row = build_sentiment_learning_feedback_row(
        decision=decision,
        sentiment_row=sample_row(),
        intended_side="LONG",
    )

    assert row.decision_id == "decision_2"
    assert row.features["fear_greed_label"] == "greed"