from ops.decision_journal import DecisionEvidence
from ops.sentiment_decision_bridge import (
    build_decision_journal_entry_with_sentiment,
    enrich_decision_evidence_with_sentiment,
)
from sentiment.sentiment_schema import SentimentFeatureRow


def test_enrich_decision_evidence_with_sentiment():
    row = SentimentFeatureRow(
        btc_sentiment_index=70,
        fear_greed_value=70,
        fear_greed_label="greed",
        sentiment_confidence=0.8,
        items_count=5,
    )

    evidence = enrich_decision_evidence_with_sentiment(
        evidence=DecisionEvidence(expected_value_usd=0.5),
        sentiment_row=row,
        intended_side="LONG",
    )

    assert getattr(evidence, "sentiment_index") == 70
    assert getattr(evidence, "fear_greed_label") == "greed"


def test_decision_journal_with_sentiment_blocks_extreme_greed_long():
    row = SentimentFeatureRow(
        btc_sentiment_index=90,
        fear_greed_value=90,
        fear_greed_label="extreme_greed",
        sentiment_confidence=0.8,
        items_count=5,
    )

    entry = build_decision_journal_entry_with_sentiment(
        decision_id="unit_sentiment_decision",
        symbol="BTCUSDT",
        side="LONG",
        evidence=DecisionEvidence(expected_value_usd=0.5),
        sentiment_row=row,
    )

    assert entry.final_decision == "BLOCK"
    assert "EXECUTION_BLOCKED" in entry.reason_codes