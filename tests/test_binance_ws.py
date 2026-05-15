from connectors.binance_ws import (
    build_combined_stream_url,
    candle_event_to_kafka,
    normalize_kline_message,
    parse_csv_env,
)


def test_parse_csv_env():
    assert parse_csv_env("5m,15m, 1h,1d") == ["5m", "15m", "1h", "1d"]


def test_build_combined_stream_url():
    url = build_combined_stream_url(
        base_url="wss://fstream.binance.com/market",
        symbol="BTCUSDT",
        intervals=["5m", "15m", "1h", "1d"],
    )

    assert url == (
        "wss://fstream.binance.com/market/stream?"
        "streams=btcusdt@kline_5m/"
        "btcusdt@kline_15m/"
        "btcusdt@kline_1h/"
        "btcusdt@kline_1d"
    )


def test_normalize_combined_kline_message():
    payload = {
        "stream": "btcusdt@kline_5m",
        "data": {
            "e": "kline",
            "E": 1638747660000,
            "s": "BTCUSDT",
            "k": {
                "t": 1638747660000,
                "T": 1638747719999,
                "s": "BTCUSDT",
                "i": "5m",
                "f": 100,
                "L": 200,
                "o": "65000.00",
                "c": "65100.00",
                "h": "65200.00",
                "l": "64900.00",
                "v": "123.45",
                "n": 321,
                "x": True,
                "q": "8025000.50",
                "V": "60.00",
                "Q": "3900000.00",
                "B": "0",
            },
        },
    }

    event = normalize_kline_message(payload)

    assert event is not None
    assert event.source == "binance_ws"
    assert event.exchange == "binance"
    assert event.market_type == "usds_m_futures"
    assert event.symbol == "BTCUSDT"
    assert event.timeframe == "5m"
    assert event.open == 65000.0
    assert event.high == 65200.0
    assert event.low == 64900.0
    assert event.close == 65100.0
    assert event.volume == 123.45
    assert event.quote_volume == 8025000.5
    assert event.trades_count == 321
    assert event.is_closed is True


def test_candle_event_to_kafka():
    payload = {
        "e": "kline",
        "E": 1638747660000,
        "s": "BTCUSDT",
        "k": {
            "t": 1638747660000,
            "T": 1638747719999,
            "s": "BTCUSDT",
            "i": "15m",
            "o": "65000.00",
            "c": "65100.00",
            "h": "65200.00",
            "l": "64900.00",
            "v": "123.45",
            "n": 321,
            "x": True,
            "q": "8025000.50",
            "V": "60.00",
            "Q": "3900000.00",
        },
    }

    event = normalize_kline_message(payload)
    kafka_event = candle_event_to_kafka(event, topic="btc-candles")

    assert kafka_event.topic == "btc-candles"
    assert kafka_event.key == "BTCUSDT:15m:1638747660000"
    assert kafka_event.value["symbol"] == "BTCUSDT"
    assert kafka_event.value["timeframe"] == "15m"