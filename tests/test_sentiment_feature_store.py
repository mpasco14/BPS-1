from data.sentiment_feature_store import (
    append_sentiment_feature_row,
    build_sentiment_feature_row,
    load_sentiment_feature_rows,
)
from sentiment.fear_greed import build_fear_greed_report
from sentiment.sentiment_index import SentimentIndexReport


def test_build_sentiment_feature_row():
    index = SentimentIndexReport(
        asset="BTCUSDT",
        timeframe="5m",
        sentiment_index=70,
        weighted_sentiment_score=0.4,
        items_count=3,
        bullish_count=2,
        bearish_count=1,
    )
    fear_greed = build_fear_greed_report(sentiment_index=index)

    row = build_sentiment_feature_row(
        sentiment_index=index,
        fear_greed=fear_greed,
    )

    assert row.btc_sentiment_index == 70
    assert row.fear_greed_label == "greed"


def test_append_and_load_sentiment_feature_row(tmp_path):
    index = SentimentIndexReport(asset="BTCUSDT", timeframe="5m", sentiment_index=70)
    fear_greed = build_fear_greed_report(sentiment_index=index)
    row = build_sentiment_feature_row(sentiment_index=index, fear_greed=fear_greed)

    path = append_sentiment_feature_row(row, path=tmp_path / "sentiment.jsonl")
    loaded = load_sentiment_feature_rows(path)

    assert path.exists()
    assert len(loaded) == 1