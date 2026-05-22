from sentiment.sentiment_schema import RawSentimentItem, SentimentClassification


def test_raw_sentiment_item():
    item = RawSentimentItem(
        item_id="1",
        source_type="x",
        source_name="x",
        text="BTC bullish",
    )

    assert item.item_id == "1"
    assert item.source_type == "x"


def test_sentiment_classification_bounds():
    item = SentimentClassification(
        item_id="1",
        source_type="news",
        source_name="news",
        sentiment="bullish",
        score=0.8,
        confidence=0.9,
    )

    assert item.score == 0.8
    assert item.confidence == 0.9