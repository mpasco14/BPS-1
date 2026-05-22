from sentiment.preprocessor import normalize_text, preprocess_sentiment_items
from sentiment.sentiment_schema import RawSentimentItem


def test_normalize_text_maps_emoji():
    assert "bullish_rocket" in normalize_text("BTC 🚀")


def test_preprocess_filters_duplicates():
    items = [
        RawSentimentItem(item_id="1", source_type="x", source_name="x", text="BTC breakout price pump", symbols=["BTCUSDT"]),
        RawSentimentItem(item_id="2", source_type="x", source_name="x", text="BTC breakout price pump", symbols=["BTCUSDT"]),
    ]

    result = preprocess_sentiment_items(items)

    assert result.clean_items_count == 1
    assert result.duplicates_count == 1


def test_preprocess_keeps_relevant_btc_text():
    items = [
        RawSentimentItem(item_id="1", source_type="news", source_name="news", text="Bitcoin ETF inflow supports BTC price", symbols=["BTCUSDT"])
    ]

    result = preprocess_sentiment_items(items)

    assert result.clean_items_count == 1