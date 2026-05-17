from backtesting.backtest import price_path_key, run_backtest
from risk.risk_manager import RiskProfile


def custom_profile():
    return RiskProfile(
        venue="binance_futures",
        symbol="BTCUSDT",
        margin_usd=20,
        leverage=30,
        notional_usd=600,
        gross_take_profit_usd=2.10,
        gross_stop_loss_usd=1.05,
        estimated_entry_fee_usd=0.05,
        estimated_exit_fee_usd=0.05,
        max_leverage=30,
        max_margin_usd=20,
        max_notional_usd=600,
        max_daily_loss_usd=5,
        max_trade_loss_usd=1.05,
        max_consecutive_losses=3,
        max_open_positions=1,
        max_open_orders=3,
        max_spread_pct=0.002,
        min_liquidity_usd=50000,
        min_confidence=0.65,
    )


def sample_feature(timestamp="2026-05-15T18:00:00+00:00", combined_score=0.9):
    return {
        "timestamp": timestamp,
        "venue": "binance_futures",
        "instrument_id": "BTCUSDT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "tech_score": 0.9,
        "microstructure_score": 0.4,
        "onchain_score": 0.05,
        "sentiment_score": 0.03,
        "combined_score": combined_score,
        "binance_spread_pct": 0.0001,
        "binance_liquidity_usd": 100000,
        "mark_price": 60000,
        "open_interest": 100000,
        "funding_rate": 0.0001,
        "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
    }


def test_price_path_key():
    feature = sample_feature()

    assert price_path_key(feature) == "BTCUSDT:5m:2026-05-15T18:00:00+00:00"


def test_run_backtest_executes_take_profit():
    feature = sample_feature()
    key = price_path_key(feature)

    report = run_backtest(
        feature_snapshots=[feature],
        price_paths={
            key: [
                {
                    "timestamp": "2026-05-15T18:05:00+00:00",
                    "high": 60300,
                    "low": 60000,
                    "close": 60300,
                },
            ]
        },
        profile=custom_profile(),
        initial_balance_usd=1000,
    )

    assert report.total_features == 1
    assert report.executed_trades == 1
    assert report.risk_approved == 1
    assert report.pnl_summary["net_pnl_usd"] > 0
    assert report.trades[0]["simulation"]["outcome"] == "take_profit"


def test_run_backtest_blocks_hold_signal():
    feature = sample_feature(combined_score=0.1)
    key = price_path_key(feature)

    report = run_backtest(
        feature_snapshots=[feature],
        price_paths={
            key: [
                {"timestamp": "2026-05-15T18:05:00+00:00", "high": 60210, "low": 60000, "close": 60210},
            ]
        },
        profile=custom_profile(),
        initial_balance_usd=1000,
    )

    assert report.total_features == 1
    assert report.executed_trades == 0
    assert report.blocked_trades == 1


def test_run_backtest_multiple_features_temporal_order():
    features = [
        sample_feature(timestamp="2026-05-15T18:05:00+00:00", combined_score=0.9),
        sample_feature(timestamp="2026-05-15T18:00:00+00:00", combined_score=0.9),
    ]

    price_paths = {}

    for feature in features:
        price_paths[price_path_key(feature)] = [
            {"timestamp": feature["timestamp"], "high": 60210, "low": 60000, "close": 60210},
        ]

    report = run_backtest(
        feature_snapshots=features,
        price_paths=price_paths,
        profile=custom_profile(),
        initial_balance_usd=1000,
    )

    assert report.total_features == 2
    assert report.executed_trades == 2