from connectors.sentiment import (
    NewsItem,
    calculate_article_sentiment_score,
    calculate_batch_sentiment,
    clamp_sentiment_score,
    contains_btc_context,
    event_to_kafka,
    find_keywords,
    parse_csv_env,
    strip_html,
)


def test_parse_csv_env():
    assert parse_csv_env("ETF,SEC, CPI") == ["ETF", "SEC", "CPI"]


def test_strip_html():
    assert strip_html("<p>Bitcoin <b>rally</b></p>") == "Bitcoin rally"


def test_contains_btc_context():
    assert contains_btc_context("Bitcoin ETF approval expected")
    assert contains_btc_context("Crypto markets rally")
    assert not contains_btc_context("Football team wins final")


def test_find_keywords():
    found = find_keywords(
        "Bitcoin ETF approval faces SEC lawsuit risk",
        ["ETF", "SEC", "lawsuit", "hack"],
    )

    assert found == ["ETF", "lawsuit", "SEC"]


def test_positive_article_sentiment():
    score, positive_hits, negative_hits, neutral_hits = calculate_article_sentiment_score(
        "Bitcoin ETF approval sparks bullish rally"
    )

    assert score > 0
    assert "approval" in positive_hits
    assert "bullish" in positive_hits
    assert negative_hits == []


def test_negative_article_sentiment():
    score, positive_hits, negative_hits, neutral_hits = calculate_article_sentiment_score(
        "Bitcoin exchange hack triggers liquidation fears and lawsuit"
    )

    assert score < 0
    assert "hack" in negative_hits
    assert "liquidation" in negative_hits
    assert "lawsuit" in negative_hits


def test_clamp_sentiment_score():
    assert clamp_sentiment_score(2.0) == 1.0
    assert clamp_sentiment_score(-2.0) == -1.0
    assert clamp_sentiment_score(0.1234567) == 0.123457


def test_calculate_batch_sentiment():
    items = [
        NewsItem(
            provider="test",
            title="Bitcoin ETF approval sparks bullish rally",
            summary="The SEC decision may improve institutional adoption.",
            url="https://example.com/1",
            published_at="2026-05-15T00:00:00+00:00",
            raw={},
        ),
        NewsItem(
            provider="test",
            title="Exchange hack triggers crypto liquidation fears",
            summary="A lawsuit may follow.",
            url="https://example.com/2",
            published_at="2026-05-15T00:00:00+00:00",
            raw={},
        ),
        NewsItem(
            provider="test",
            title="Football team wins final",
            summary="Sports news.",
            url="https://example.com/3",
            published_at="2026-05-15T00:00:00+00:00",
            raw={},
        ),
    ]

    event = calculate_batch_sentiment(
        items=items,
        tracked_keywords=["ETF", "SEC", "hack", "liquidation", "lawsuit", "approval"],
    )

    assert event.event_type == "sentiment_snapshot"
    assert event.asset == "BTC"
    assert event.volume_mentions == 2
    assert "ETF" in event.keywords
    assert "hack" in event.keywords
    assert len(event.articles) == 2


def test_event_to_kafka():
    items = [
        NewsItem(
            provider="test",
            title="Bitcoin ETF approval sparks bullish rally",
            summary="",
            url="https://example.com/1",
            published_at=None,
            raw={},
        )
    ]

    event = calculate_batch_sentiment(
        items=items,
        tracked_keywords=["ETF", "approval"],
    )

    kafka_event = event_to_kafka(event, topic="sentiment-events")

    assert kafka_event.topic == "sentiment-events"
    assert kafka_event.value["event_type"] == "sentiment_snapshot"
    assert kafka_event.value["asset"] == "BTC"