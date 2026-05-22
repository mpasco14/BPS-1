from datetime import datetime, timezone

from sentiment.sentiment_schema import SentimentClassification
from sentiment.source_weighting import SourceWeightConfig, apply_source_weights, calculate_source_weight


def test_calculate_source_weight():
    item = SentimentClassification(
        item_id="1",
        source_type="news",
        source_name="tier1",
        sentiment="bullish",
        score=0.8,
        confidence=1.0,
        created_at=datetime.now(timezone.utc),
        metadata={"source_tier": "tier1"},
    )

    weight = calculate_source_weight(
        item,
        config=SourceWeightConfig(time_decay_halflife_minutes=60),
        now=datetime.now(timezone.utc),
    )

    assert weight > 0


def test_apply_source_weights_sets_weighted_score():
    item = SentimentClassification(
        item_id="1",
        source_type="x",
        source_name="x",
        sentiment="bullish",
        score=0.5,
        confidence=1.0,
    )

    weighted = apply_source_weights([item])

    assert weighted[0].weight > 0
    assert weighted[0].weighted_score > 0