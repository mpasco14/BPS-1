from scenario_testing.news_sentiment_shock_scenario import run_news_sentiment_shock_scenario


def test_news_sentiment_shock_blocks_extreme_sentiment():
    report = run_news_sentiment_shock_scenario()

    assert report.passed is True
    assert report.metadata["news_events"] > 0
    assert report.metadata["sentiment_blocks"] > 0
    assert "extreme_sentiment_blocks_confirmed" in report.warnings