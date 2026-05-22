from sentiment.sentiment_orchestrator import build_demo_raw_items, run_sentiment_orchestrator


def test_sentiment_orchestrator_demo():
    report = run_sentiment_orchestrator(
        raw_items=build_demo_raw_items(),
        asset="BTCUSDT",
        timeframe="5m",
    )

    assert report.raw_items_count == 3
    assert report.clean_items_count >= 1
    assert "sentiment_index" in report.model_dump()