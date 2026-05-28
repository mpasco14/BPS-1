from system_integration.sentiment_journal_integration import (
    SentimentNoTradeInput,
    integrate_sentiment_no_trade_journal,
)


def test_sentiment_journal_allows_neutral_sentiment():
    report = integrate_sentiment_no_trade_journal(
        sentiment=SentimentNoTradeInput(regime="neutral", confidence=0.8)
    )

    assert report.approved_for_signal is True
    assert report.journal_entry["decision"] == "SENTIMENT_ACCEPTED"


def test_sentiment_journal_blocks_extreme_fear():
    report = integrate_sentiment_no_trade_journal(
        sentiment=SentimentNoTradeInput(regime="extreme_fear", confidence=0.8)
    )

    assert report.approved_for_signal is False
    assert "extreme_fear_blocks_new_entries" in report.blockers