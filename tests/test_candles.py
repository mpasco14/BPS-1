from strategy.candles import (
    Candle,
    CandleSeriesStore,
    build_candle_from_normalized_event,
)


def sample_candle(open_time=1, close=101.0, timeframe="5m", is_closed=True):
    return {
        "venue": "binance_futures",
        "symbol": "btcusdt",
        "timeframe": timeframe,
        "open_time": open_time,
        "close_time": open_time + 299,
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": close,
        "volume": 10.0,
        "quote_volume": 1000.0,
        "trades_count": 100,
        "is_closed": is_closed,
        "funding_rate": 0.0001,
        "open_interest": 100000.0,
        "mark_price": close,
        "index_price": close,
    }


def test_candle_validation_normalizes_symbol_and_timeframe():
    candle = Candle.model_validate(sample_candle(timeframe="1D"))

    assert candle.symbol == "BTCUSDT"
    assert candle.timeframe == "1d"
    assert candle.close == 101.0


def test_add_and_get_candles():
    store = CandleSeriesStore(timeframes=["5m"], max_candles=500)

    store.add_candle("5m", sample_candle(open_time=1))
    store.add_candle("5m", sample_candle(open_time=2))

    candles = store.get_candles("5m", 2)

    assert len(candles) == 2
    assert candles[0].open_time == 1
    assert candles[1].open_time == 2


def test_duplicate_open_time_replaces_existing_candle():
    store = CandleSeriesStore(timeframes=["5m"], max_candles=500)

    store.add_candle("5m", sample_candle(open_time=1, close=101.0, is_closed=False))
    store.add_candle("5m", sample_candle(open_time=1, close=105.0, is_closed=True))

    candles = store.get_candles("5m")

    assert len(candles) == 1
    assert candles[0].close == 105.0
    assert candles[0].is_closed is True


def test_buffer_respects_max_size():
    store = CandleSeriesStore(timeframes=["5m"], max_candles=3)

    for index in range(5):
        store.add_candle("5m", sample_candle(open_time=index, close=100 + index))

    candles = store.get_candles("5m")

    assert len(candles) == 3
    assert [candle.open_time for candle in candles] == [2, 3, 4]


def test_get_latest():
    store = CandleSeriesStore(timeframes=["5m"], max_candles=500)

    store.add_candle("5m", sample_candle(open_time=1, close=101.0))
    store.add_candle("5m", sample_candle(open_time=2, close=102.0))

    latest = store.get_latest("5m")

    assert latest is not None
    assert latest.open_time == 2
    assert latest.close == 102.0


def test_is_ready_for_ema200():
    store = CandleSeriesStore(
        timeframes=["5m"],
        max_candles=500,
        min_candles_for_ema200=200,
    )

    for index in range(199):
        store.add_candle("5m", sample_candle(open_time=index))

    assert store.is_ready("5m") is False

    store.add_candle("5m", sample_candle(open_time=199))

    assert store.is_ready("5m") is True


def test_to_dataframe():
    store = CandleSeriesStore(timeframes=["5m"], max_candles=500)

    store.add_candle("5m", sample_candle(open_time=1))
    store.add_candle("5m", sample_candle(open_time=2))

    df = store.to_dataframe("5m")

    assert len(df) == 2
    assert list(df["close"]) == [101.0, 101.0]
    assert "volume" in df.columns


def test_stats():
    store = CandleSeriesStore(timeframes=["5m"], max_candles=500)

    store.add_candle("5m", sample_candle(open_time=1, close=101.0))

    stats = store.stats("5m")

    assert stats.timeframe == "5m"
    assert stats.size == 1
    assert stats.latest_close == 101.0
    assert stats.ready_for_ema200 is False


def test_build_candle_from_normalized_event():
    event = {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "open_time": "2026-05-15T18:00:00+00:00",
        "close_time": "2026-05-15T18:14:59+00:00",
        "open": 65000.0,
        "high": 65200.0,
        "low": 64900.0,
        "close": 65100.0,
        "volume": 123.45,
        "quote_volume": 8025000.5,
        "trades_count": 321,
        "is_closed": True,
        "funding_rate": 0.00001,
        "open_interest": 102140.579,
        "mark_price": 79189.11,
        "index_price": 79227.26,
        "received_at": "2026-05-15T18:31:00+00:00",
        "raw": {"example": True},
    }

    candle = build_candle_from_normalized_event(event)

    assert candle.venue == "binance_futures"
    assert candle.symbol == "BTCUSDT"
    assert candle.timeframe == "15m"
    assert candle.close == 65100.0