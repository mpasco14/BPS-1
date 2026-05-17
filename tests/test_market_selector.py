from execution.market_selector import (
    classify_timeframe_from_text,
    normalize_timeframe,
    select_markets_from_exchange_info,
)


def sample_exchange_info():
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "filters": [],
            },
            {
                "symbol": "ETHUSDT",
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "filters": [],
            },
            {
                "symbol": "BTCBUSD",
                "status": "BREAK",
                "contractType": "PERPETUAL",
                "baseAsset": "BTC",
                "quoteAsset": "BUSD",
                "filters": [],
            },
        ]
    }


def test_normalize_timeframe():
    assert normalize_timeframe("5M") == "5m"
    assert normalize_timeframe("15m") == "15m"
    assert normalize_timeframe("1H") == "1h"
    assert normalize_timeframe("1D") == "1d"


def test_classify_timeframe_from_text():
    assert classify_timeframe_from_text("BTC 5 minute market") == "5m"
    assert classify_timeframe_from_text("BTC hourly setup") == "1h"
    assert classify_timeframe_from_text("BTC daily setup") == "1d"


def test_select_markets_from_exchange_info():
    markets = select_markets_from_exchange_info(
        sample_exchange_info(),
        symbols=["BTCUSDT"],
        timeframes=["5m", "15m"],
    )

    assert len(markets) == 1
    assert markets[0].symbol == "BTCUSDT"
    assert markets[0].timeframes == ["5m", "15m"]