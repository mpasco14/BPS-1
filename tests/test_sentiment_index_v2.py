from sentiment.sentiment_index import build_sentiment_index
from sentiment.sentiment_schema import SentimentClassification


def test_build_sentiment_index_bullish():
    report = build_sentiment_index(
        items=[
            SentimentClassification(
                item_id="1",
                source_type="news",
                source_name="news",
                sentiment="bullish",
                score=0.8,
                confidence=1.0,
                weight=1.0,
            )
        ]
    )

    assert report.sentiment_index > 50
    assert report.bullish_count == 1


def test_build_sentiment_index_empty():
    report = build_sentiment_index(items=[])

    assert report.sentiment_index == 50
    assert report.items_count == 0