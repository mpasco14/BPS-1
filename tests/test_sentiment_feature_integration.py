from sentiment.feature_integration import (
    build_signal_engine_payload_with_sentiment,
    evaluate_sentiment_signal_context,
    merge_sentiment_features,
)
from sentiment.sentiment_schema import SentimentFeatureRow


def sample_row():
    return SentimentFeatureRow(
        symbol="BTCUSDT",
        timeframe="5m",
        btc_sentiment_index=70,
        fear_greed_value=70,
        fear_greed_label="greed",
        sentiment_confidence=0.8,
        items_count=3,
    )


def test_merge_sentiment_features():
    merged = merge_sentiment_features(
        base_features={"symbol": "BTCUSDT"},
        sentiment_row=sample_row(),
    )

    assert merged["btc_sentiment_index"] == 70
    assert "sentiment_v2" in merged


def test_evaluate_sentiment_signal_context_boost_long():
    context = evaluate_sentiment_signal_context(
        sentiment_row=sample_row(),
        side="LONG",
    )

    assert context.action == "BOOST_LONG"
    assert context.should_block is False


def test_build_signal_engine_payload_with_sentiment():
    payload = build_signal_engine_payload_with_sentiment(
        base_features={"symbol": "BTCUSDT"},
        sentiment_row=sample_row(),
        side="LONG",
    )

    assert payload["sentiment_signal_context"]["action"] == "BOOST_LONG"