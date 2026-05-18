from execution.limit_order import rules_from_symbol_info
from backtesting.full_backtest import (
    FullBacktestCostModel,
    calculate_max_drawdown_pct,
    calculate_profit_factor,
    export_full_backtest_report,
    run_full_backtest,
)
from risk.exposure import ExposureSnapshot
from risk.risk_manager import RiskProfile
from execution.paper_trading_loop import price_path_key


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
        max_daily_loss_usd=60,
        max_trade_loss_usd=2,
        max_consecutive_losses=3,
        max_open_positions=5,
        max_open_orders=5,
        max_spread_pct=0.002,
        min_liquidity_usd=50000,
        min_confidence=0.65,
    )


def exposure():
    return ExposureSnapshot(
        total_bankroll_usd=2000,
        daily_pnl_usd=0,
        open_positions=0,
        exposure_per_market={},
        exposure_by_timeframe={},
        btc_directional_exposure_usd=0,
    )


def symbol_rules():
    return rules_from_symbol_info(
        {
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ],
        }
    )


def feature(timestamp="2026-05-15T18:00:00+00:00", score=0.9):
    sign = 1 if score >= 0 else -1

    return {
        "timestamp": timestamp,
        "venue": "binance_futures",
        "instrument_id": "BTCUSDT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "tech_score": 0.9 * sign,
        "microstructure_score": 0.4 * sign,
        "onchain_score": 0.05 * sign,
        "sentiment_score": 0.03 * sign,
        "combined_score": score,
        "binance_spread_pct": 0.0001,
        "binance_liquidity_usd": 100000,
        "mark_price": 60000,
        "expected_value_usd": 0.50,
        "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
    }


def test_calculate_max_drawdown_pct():
    equity = [1000, 1100, 1050, 900, 1200]

    assert calculate_max_drawdown_pct(equity) == 200 / 1100


def test_calculate_profit_factor():
    assert calculate_profit_factor([2, -1, 3]) == 5


def test_run_full_backtest():
    features = [
        feature("2026-05-15T18:00:00+00:00", 0.9),
        feature("2026-05-15T18:05:00+00:00", -0.9),
        feature("2026-05-15T18:10:00+00:00", 0.1),
    ]

    price_paths = {}

    for item in features:
        price_paths[price_path_key(item)] = [
            {
                "timestamp": item["timestamp"],
                "high": 60500,
                "low": 59500,
                "close": 60200,
            }
        ]

    report = run_full_backtest(
        feature_snapshots=features,
        price_paths=price_paths,
        rules=symbol_rules(),
        profile=custom_profile(),
        exposure_snapshot=exposure(),
        initial_balance_usd=2000,
        cost_model=FullBacktestCostModel(
            slippage_pct=0.0,
            partial_fill_ratio=1.0,
        ),
    )

    assert report.metrics["routed_orders"] >= 1
    assert report.metrics["total_trades"] >= 1
    assert "5m" in report.metrics["pnl_by_timeframe"]
    assert report.cost_model["latency_ms"] == 200


def test_export_full_backtest_report(tmp_path):
    features = [feature()]
    key = price_path_key(features[0])

    report = run_full_backtest(
        feature_snapshots=features,
        price_paths={
            key: [
                {
                    "timestamp": "2026-05-15T18:05:00+00:00",
                    "high": 60500,
                    "low": 60000,
                    "close": 60500,
                }
            ]
        },
        rules=symbol_rules(),
        profile=custom_profile(),
        exposure_snapshot=exposure(),
        initial_balance_usd=2000,
        cost_model=FullBacktestCostModel(
            slippage_pct=0.0,
            partial_fill_ratio=0.5,
        ),
    )

    paths = export_full_backtest_report(report, output_dir=tmp_path)

    assert paths["summary"].exists()
    assert paths["trades"].exists()