import json

from data.candle_store import (
    CandleStoreService,
    build_candle_redis_key,
    candle_to_redis_json,
    candle_to_timescale_row,
    parse_message_value,
    validate_candle_event,
)


def sample_candle_payload():
    return {
        "source": "binance_ws",
        "exchange": "binance",
        "market_type": "usds_m_futures",
        "symbol": "btcusdt",
        "timeframe": "5m",
        "open_time": 1638747660000,
        "close_time": 1638747719999,
        "event_time": 1638747660000,
        "open": 65000.0,
        "high": 65200.0,
        "low": 64900.0,
        "close": 65100.0,
        "volume": 123.45,
        "quote_volume": 8025000.5,
        "trades_count": 321,
        "taker_buy_base_volume": 60.0,
        "taker_buy_quote_volume": 3900000.0,
        "is_closed": True,
        "funding_rate": 0.00001,
        "funding_time": 1778860800012,
        "open_interest": 102140.579,
        "mark_price": 79189.11,
        "index_price": 79227.26,
        "next_funding_time": 1778889600000,
        "metrics_collected_at": "2026-05-15T18:30:39.924612+00:00",
        "received_at": "2026-05-15T18:31:00+00:00",
        "raw": {"example": True},
    }


def test_parse_message_value_from_bytes():
    payload = sample_candle_payload()
    raw = json.dumps(payload).encode("utf-8")

    parsed = parse_message_value(raw)

    assert parsed["symbol"] == "btcusdt"
    assert parsed["timeframe"] == "5m"


def test_validate_candle_event_normalizes_symbol():
    candle = validate_candle_event(sample_candle_payload())

    assert candle.symbol == "BTCUSDT"
    assert candle.timeframe == "5m"
    assert candle.close == 65100.0
    assert candle.is_closed is True


def test_build_candle_redis_key():
    key = build_candle_redis_key(
        symbol="btcusdt",
        timeframe="5m",
        prefix="btc_poly_bot",
        environment="dev",
    )

    assert key == "btc_poly_bot:dev:btc_candle:BTCUSDT:5m"


def test_candle_to_redis_json():
    candle = validate_candle_event(sample_candle_payload())
    encoded = candle_to_redis_json(candle)
    decoded = json.loads(encoded)

    assert decoded["symbol"] == "BTCUSDT"
    assert decoded["timeframe"] == "5m"
    assert decoded["close"] == 65100.0


def test_candle_to_timescale_row():
    candle = validate_candle_event(sample_candle_payload())
    row = candle_to_timescale_row(candle)

    assert row["symbol"] == "BTCUSDT"
    assert row["timeframe"] == "5m"
    assert row["open_time"] == 1638747660000
    assert row["mark_price"] == 79189.11


def test_candle_store_service_writes_to_fake_redis_store():
    class FakeRedisStore:
        def __init__(self):
            self.written = []

        def write_latest(self, candle):
            self.written.append(candle)
            return f"fake:{candle.symbol}:{candle.timeframe}"

    fake_store = FakeRedisStore()

    service = CandleStoreService(
        redis_store=fake_store,
        write_redis=True,
        write_timescale=False,
    )

    candle = service.process_message_value(json.dumps(sample_candle_payload()))

    assert candle.symbol == "BTCUSDT"
    assert len(fake_store.written) == 1
    assert fake_store.written[0].timeframe == "5m"