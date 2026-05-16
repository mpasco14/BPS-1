import numpy as np
import pandas as pd

from strategy.technical_engine import (
    adx,
    atr,
    calculate_technical_snapshot,
    ema,
    macd,
    normalize_timeframe,
    prepare_ohlcv_dataframe,
    rsi,
    vwap,
    weighted_score,
)


def make_ohlcv(rows=250, timeframe="5m", trend=1.0):
    base = np.linspace(60000, 61000 * trend, rows)

    data = {
        "open_time": list(range(rows)),
        "close_time": list(range(rows)),
        "open": base,
        "high": base + 100,
        "low": base - 100,
        "close": base + np.sin(np.arange(rows)) * 10,
        "volume": np.linspace(10, 100, rows),
        "quote_volume": np.linspace(600000, 6100000, rows),
        "trades_count": list(range(rows)),
        "funding_rate": [0.0001] * rows,
        "open_interest": [100000.0] * rows,
        "mark_price": base,
        "index_price": base,
        "timeframe": [timeframe] * rows,
    }

    return pd.DataFrame(data)


def test_normalize_timeframe():
    assert normalize_timeframe("5M") == "5m"
    assert normalize_timeframe("15m") == "15m"
    assert normalize_timeframe("1H") == "1h"
    assert normalize_timeframe("1D") == "1d"


def test_prepare_ohlcv_dataframe():
    df = make_ohlcv(rows=10)
    prepared = prepare_ohlcv_dataframe(df)

    assert len(prepared) == 10
    assert prepared["close"].dtype.kind in {"f", "i"}


def test_ema_calculation():
    df = make_ohlcv(rows=50)
    result = ema(df["close"], 9)

    assert len(result) == 50
    assert result.iloc[-1] > 0


def test_rsi_calculation():
    df = make_ohlcv(rows=50)
    result = rsi(df["close"], 14)

    assert len(result) == 50
    assert 0 <= result.iloc[-1] <= 100


def test_macd_calculation():
    df = make_ohlcv(rows=100)
    macd_line, signal_line, hist = macd(df["close"])

    assert len(macd_line) == 100
    assert len(signal_line) == 100
    assert len(hist) == 100


def test_atr_calculation():
    df = make_ohlcv(rows=50)
    result = atr(df, 14)

    assert len(result) == 50
    assert result.iloc[-1] > 0


def test_vwap_calculation():
    df = make_ohlcv(rows=50)
    result = vwap(df)

    assert len(result) == 50
    assert result.iloc[-1] > 0


def test_adx_calculation():
    df = make_ohlcv(rows=100)
    result = adx(df, 14)

    assert len(result) == 100
    assert result.iloc[-1] >= 0


def test_weighted_score_bounds():
    score = weighted_score(
        signals={
            "ema_signal": 1,
            "vwap_signal": 1,
            "rsi_signal": 1,
        },
        weights={
            "ema_signal": 0.3,
            "vwap_signal": 0.3,
            "rsi_signal": 0.4,
        },
    )

    assert -1 <= score <= 1
    assert score == 1


def test_calculate_technical_snapshot_5m():
    df = make_ohlcv(rows=250, timeframe="5m")

    snapshot = calculate_technical_snapshot(
        timeframe="5m",
        candles=df,
        symbol="BTCUSDT",
    )

    assert snapshot.timeframe == "5m"
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.row_count == 250
    assert -1 <= snapshot.technical_score <= 1
    assert "ema_signal" in snapshot.signals
    assert "vwap_signal" in snapshot.signals
    assert "rsi_signal" in snapshot.signals


def test_calculate_technical_snapshot_15m():
    df = make_ohlcv(rows=250, timeframe="15m")

    snapshot = calculate_technical_snapshot(
        timeframe="15m",
        candles=df,
        symbol="BTCUSDT",
    )

    assert snapshot.timeframe == "15m"
    assert -1 <= snapshot.technical_score <= 1
    assert "bb_signal" in snapshot.signals
    assert "adx_signal" in snapshot.signals


def test_calculate_technical_snapshot_1h():
    df = make_ohlcv(rows=250, timeframe="1h")

    snapshot = calculate_technical_snapshot(
        timeframe="1h",
        candles=df,
        symbol="BTCUSDT",
    )

    assert snapshot.timeframe == "1h"
    assert snapshot.is_ready is True
    assert "funding_rate_signal" in snapshot.signals
    assert -1 <= snapshot.technical_score <= 1


def test_calculate_technical_snapshot_1d():
    df = make_ohlcv(rows=250, timeframe="1d")
    df["onchain_flow_signal"] = 0.25

    snapshot = calculate_technical_snapshot(
        timeframe="1d",
        candles=df,
        symbol="BTCUSDT",
    )

    assert snapshot.timeframe == "1d"
    assert snapshot.is_ready is True
    assert "realized_vol_signal" in snapshot.signals
    assert "onchain_flow_signal" in snapshot.signals
    assert -1 <= snapshot.technical_score <= 1