from data.normalizer import (
    ForwardFillState,
    event_to_dict,
    infer_event_kind,
    normalize_candle_event,
    normalize_event,
    normalize_onchain_event,
    normalize_orderbook_event,
    normalize_sentiment_event,
    normalize_timeframe,
    safe_float,
    timestamp_to_utc_iso,
)


def sample_candle_raw():
    return {
        "source": "binance_ws",
        "exchange": "binance",
        "market_type": "usds_m_futures",
        "symbol": "btcusdt",
        "timeframe": "5m",
        "open_time": 1638747660000,
        "close_time": 1638747719999,
        "event_time": 1638747660000,
        "open": "65000.00",
        "high": "65200.00",
        "low": "64900.00",
        "close": "65100.00",
        "volume": "123.45",
        "quote_volume": "8025000.50",
        "trades_count": 321,
        "is_closed": True,
        "funding_rate": "0.00001",
        "open_interest": "102140.579",
        "mark_price": "79189.11",
        "index_price": "79227.26",
        "received_at": "2026-05-15T18:31:00+00:00",
    }


def test_safe_float():
    assert safe_float("1.23") == 1.23
    assert safe_float(None) is None
    assert safe_float("abc") is None


def test_timestamp_to_utc_iso_from_milliseconds():
    value = timestamp_to_utc_iso(1638747660000)

    assert value.startswith("2021-12")


def test_normalize_timeframe():
    assert normalize_timeframe("1D") == "1d"
    assert normalize_timeframe("1h") == "1h"
    assert normalize_timeframe("15m") == "15m"


def test_infer_event_kind_candle():
    assert infer_event_kind(sample_candle_raw()) == "candle"


def test_normalize_candle_event():
    event = normalize_candle_event(sample_candle_raw())

    assert event.event_kind == "candle"
    assert event.symbol == "BTCUSDT"
    assert event.timeframe == "5m"
    assert event.open == 65000.0
    assert event.close == 65100.0
    assert event.funding_rate == 0.00001
    assert event.open_interest == 102140.579


def test_normalize_orderbook_event():
    raw = {
        "source": "polymarket_ws",
        "channel": "market",
        "event_type": "best_bid_ask",
        "market": "0xmarket",
        "asset_id": "token_yes",
        "best_bid": "0.48",
        "best_ask": "0.52",
        "received_at": "2026-05-15T18:31:00+00:00",
    }

    event = normalize_orderbook_event(raw)

    assert event.event_kind == "orderbook"
    assert event.market == "0xmarket"
    assert event.asset_id == "token_yes"
    assert event.best_bid == 0.48
    assert event.best_ask == 0.52
    assert event.spread == 0.04
    assert event.mid_price == 0.5


def test_normalize_onchain_event():
    raw = {
        "source": "free_onchain",
        "provider": "mempool_space",
        "event_type": "mempool_fees",
        "asset": "BTC",
        "category": "bitcoin_network",
        "interval": "snapshot",
        "timestamp": 1778869262,
        "value": {"fastestFee": 10},
        "score": 0.1,
        "collected_at": "2026-05-15T18:31:00+00:00",
    }

    event = normalize_onchain_event(raw)

    assert event.event_kind == "onchain"
    assert event.asset == "BTC"
    assert event.metric == "mempool_fees"
    assert event.score == 0.1


def test_normalize_sentiment_event():
    raw = {
        "source": "sentiment",
        "provider": "cointelegraph+decrypt",
        "event_type": "sentiment_snapshot",
        "asset": "BTC",
        "category": "social_news_sentiment",
        "interval": "snapshot",
        "timestamp": 1778869262,
        "sentiment_score": 0.25,
        "volume_mentions": 3,
        "keywords": ["ETF", "SEC"],
        "positive_hits": ["approval"],
        "negative_hits": [],
        "neutral_hits": ["ETF", "SEC"],
        "collected_at": "2026-05-15T18:31:00+00:00",
    }

    event = normalize_sentiment_event(raw)

    assert event.event_kind == "sentiment"
    assert event.asset == "BTC"
    assert event.sentiment_score == 0.25
    assert event.volume_mentions == 3
    assert "ETF" in event.keywords


def test_normalize_event_auto_infer():
    event = normalize_event(sample_candle_raw())

    assert event.event_kind == "candle"


def test_forward_fill_allowed_field():
    state = ForwardFillState(
        allowed_fields=["funding_rate"],
        max_age_seconds=60,
    )

    first = state.update_and_fill(
        entity_key="BTCUSDT:5m",
        values={"funding_rate": 0.01},
        now=100,
    )

    second = state.update_and_fill(
        entity_key="BTCUSDT:5m",
        values={"funding_rate": None},
        now=120,
    )

    assert first["funding_rate"] == 0.01
    assert second["funding_rate"] == 0.01


def test_forward_fill_expired_field():
    state = ForwardFillState(
        allowed_fields=["funding_rate"],
        max_age_seconds=10,
    )

    state.update_and_fill(
        entity_key="BTCUSDT:5m",
        values={"funding_rate": 0.01},
        now=100,
    )

    second = state.update_and_fill(
        entity_key="BTCUSDT:5m",
        values={"funding_rate": None},
        now=120,
    )

    assert second["funding_rate"] is None


def test_event_to_dict():
    event = normalize_candle_event(sample_candle_raw())
    payload = event_to_dict(event)

    assert payload["event_kind"] == "candle"
    assert payload["symbol"] == "BTCUSDT"