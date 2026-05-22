from sentiment.fear_greed import build_fear_greed_report, classify_fear_greed
from sentiment.sentiment_index import SentimentIndexReport


def test_classify_fear_greed():
    assert classify_fear_greed(10) == "extreme_fear"
    assert classify_fear_greed(50) == "neutral"
    assert classify_fear_greed(90) == "extreme_greed"


def test_build_fear_greed_report():
    report = build_fear_greed_report(
        sentiment_index=SentimentIndexReport(sentiment_index=75, panic_score=0, euphoria_score=50)
    )

    assert report.label == "greed"
    assert report.value == 75