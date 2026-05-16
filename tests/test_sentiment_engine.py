from strategy.sentiment_engine import (
    SentimentEvent,
    calculate_many_timeframes,
    calculate_mention_amplifier,
    calculate_moving_average_score,
    calculate_sentiment_snapshot,
    filter_events_by_window,
    get_timeframe_weight,
    normalize_sentiment_event,
    normalize_timeframe,
    parse_timestamp_seconds,
    snapshot_to_dict,
)


def sample_event(
    *,
    score=0.4,
    volume_mentions=10,
    timestamp=1000,
    keywords=None,
    positive_hits=None,
    negative_hits=None,
):
    return {
        "source": "sentiment",
        "provider": "rss",
        "event_type": "sentiment_snapshot",
        "asset": "BTC",
        "category": "social_news_sentiment",
        "interval": "snapshot",
        "timestamp": timestamp,
        "sentiment_score": score,
        "volume_mentions": volume_mentions,
        "keywords": keywords or ["ETF", "SEC"],
        "positive_hits": positive_hits or ["approval"],
        "negative_hits": negative_hits or [],
        "neutral_hits": ["ETF", "SEC"],
        "articles": [],
    }


def test_normalize_timeframe():
    assert normalize_timeframe("5M") == "5m"
    assert normalize_timeframe("15m") == "15m"
    assert normalize_timeframe("1H") == "1h"
    assert normalize_timeframe("1D") == "1d"


def test_parse_timestamp_seconds():
    assert parse_timestamp_seconds(1000) == 1000
    assert parse_timestamp_seconds(1000000000000) == 1000000000
    assert parse_timestamp_seconds("1000") == 1000
    assert parse_timestamp_seconds("2026-05-15T18:31:00+00:00") is not None


def test_get_timeframe_weight():
    assert get_timeframe_weight("5m") == 0.03
    assert get_timeframe_weight("15m") == 0.05
    assert get_timeframe_weight("1h") == 0.10
    assert get_timeframe_weight("1d") == 0.20


def test_normalize_sentiment_event():
    event = normalize_sentiment_event(sample_event())

    assert event.source == "sentiment"
    assert event.provider == "rss"
    assert event.asset == "BTC"
    assert event.sentiment_score == 0.4
    assert event.volume_mentions == 10


def test_filter_events_by_window_keeps_recent():
    events = [
        SentimentEvent(sentiment_score=0.2, volume_mentions=1, timestamp=600),
        SentimentEvent(sentiment_score=-0.2, volume_mentions=1, timestamp=2000),
    ]

    filtered = filter_events_by_window(
        events,
        window_minutes=30,
        now_ts=2500,
    )

    assert len(filtered) == 1
    assert filtered[0].timestamp == 2000


def test_calculate_moving_average_score():
    events = [
        SentimentEvent(sentiment_score=0.5, volume_mentions=1),
        SentimentEvent(sentiment_score=-0.1, volume_mentions=1),
    ]

    assert calculate_moving_average_score(events) == 0.2


def test_calculate_mention_amplifier():
    low = calculate_mention_amplifier(0, baseline=10, max_amplifier=1.5)
    high = calculate_mention_amplifier(10, baseline=10, max_amplifier=1.5)

    assert low == 1.0
    assert high == 1.5


def test_volume_mentions_amplifies_strength_not_direction():
    positive = calculate_sentiment_snapshot(
        timeframe="1h",
        events=[sample_event(score=0.4, volume_mentions=10, timestamp=1000)],
        now_ts=1000,
    )

    negative = calculate_sentiment_snapshot(
        timeframe="1h",
        events=[sample_event(score=-0.4, volume_mentions=10, timestamp=1000)],
        now_ts=1000,
    )

    assert positive.sentiment_score > 0
    assert negative.sentiment_score < 0
    assert abs(positive.sentiment_score) == abs(negative.sentiment_score)


def test_calculate_sentiment_snapshot_5m_small_weight():
    snapshot = calculate_sentiment_snapshot(
        timeframe="5m",
        events=[sample_event(score=0.5, volume_mentions=10, timestamp=1000)],
        now_ts=1000,
    )

    assert snapshot.source == "sentiment_engine"
    assert snapshot.venue == "binance_futures"
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.timeframe == "5m"
    assert snapshot.timeframe_weight == 0.03
    assert snapshot.is_ready is True
    assert -1 <= snapshot.sentiment_score <= 1


def test_1d_has_larger_sentiment_weight_than_5m():
    events = [sample_event(score=0.5, volume_mentions=10, timestamp=1000)]

    snap_5m = calculate_sentiment_snapshot(
        timeframe="5m",
        events=events,
        now_ts=1000,
    )

    snap_1d = calculate_sentiment_snapshot(
        timeframe="1d",
        events=events,
        now_ts=1000,
    )

    assert abs(snap_1d.sentiment_score) > abs(snap_5m.sentiment_score)


def test_keyword_hits():
    snapshot = calculate_sentiment_snapshot(
        timeframe="1h",
        events=[
            sample_event(
                score=-0.5,
                volume_mentions=10,
                timestamp=1000,
                keywords=["hack", "ETF"],
                positive_hits=[],
                negative_hits=["hack"],
            )
        ],
        now_ts=1000,
    )

    assert "hack" in snapshot.risk_keyword_hits


def test_calculate_many_timeframes():
    snapshots = calculate_many_timeframes(
        [sample_event(score=0.5, volume_mentions=10, timestamp=1000)],
        now_ts=1000,
    )

    assert set(snapshots.keys()) == {"5m", "15m", "1h", "1d"}
    assert snapshots["5m"].timeframe_weight == 0.03
    assert snapshots["1d"].timeframe_weight == 0.20


def test_snapshot_to_dict():
    snapshot = calculate_sentiment_snapshot(
        timeframe="15m",
        events=[sample_event(score=0.5, volume_mentions=10, timestamp=1000)],
        now_ts=1000,
    )

    payload = snapshot_to_dict(snapshot)

    assert payload["source"] == "sentiment_engine"
    assert payload["timeframe"] == "15m"
    assert "sentiment_score" in payload