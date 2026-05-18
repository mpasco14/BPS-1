from pathlib import Path

from execution.limit_order import rules_from_symbol_info
from execution.paper_trading_loop import (
    export_paper_trading_report,
    load_paper_trading_trades,
    price_path_key,
    run_paper_trading_session,
)
from risk.exposure import ExposureSnapshot
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


def sample_feature(timestamp="2026-05-15T18:00:00+00:00", combined_score=0.9):
    return {
        "timestamp": timestamp,
        "venue": "binance_futures",
        "instrument_id": "BTCUSDT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "tech_score": 0.9 if combined_score > 0 else -0.9,
        "microstructure_score": 0.4 if combined_score > 0 else -0.4,
        "onchain_score": 0.05 if combined_score > 0 else -0.05,
        "sentiment_score": 0.03 if combined_score > 0 else -0.03,
        "combined_score": combined_score,
        "binance_spread_pct": 0.0001,
        "binance_liquidity_usd": 100000,
        "mark_price": 60000,
        "expected_value_usd": 0.50,
        "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
    }


def test_run_paper_trading_session_routes_and_simulates_tp():
    feature = sample_feature()
    key = price_path_key(feature)

    report = run_paper_trading_session(
        feature_snapshots=[feature],
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
        estimated_slippage_pct=0.0,
        initial_balance_usd=2000,
    )

    assert report.metrics["total_features"] == 1
    assert report.metrics["routed_orders"] == 1
    assert report.metrics["blocked_orders"] == 0
    assert report.metrics["fill_rate"] == 1.0
    assert report.trades[0]["order_would_send"]["symbol"] == "BTCUSDT"
    assert report.trades[0]["market_would_do"]["outcome"] == "take_profit"
    assert report.metrics["net_pnl_usd"] > 0


def test_run_paper_trading_session_blocks_hold_signal():
    feature = sample_feature(combined_score=0.1)
    key = price_path_key(feature)

    report = run_paper_trading_session(
        feature_snapshots=[feature],
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
        estimated_slippage_pct=0.0,
    )

    assert report.metrics["routed_orders"] == 0
    assert report.metrics["blocked_orders"] == 1
    assert report.trades[0]["blocked"] is True


def test_run_paper_trading_session_multiple_features():
    features = [
        sample_feature(timestamp="2026-05-15T18:00:00+00:00", combined_score=0.9),
        sample_feature(timestamp="2026-05-15T18:05:00+00:00", combined_score=-0.9),
        sample_feature(timestamp="2026-05-15T18:10:00+00:00", combined_score=0.1),
    ]

    price_paths = {}

    for feature in features:
        price_paths[price_path_key(feature)] = [
            {
                "timestamp": feature["timestamp"],
                "high": 60500,
                "low": 59500,
                "close": 60200,
            }
        ]

    report = run_paper_trading_session(
        feature_snapshots=features,
        price_paths=price_paths,
        rules=symbol_rules(),
        profile=custom_profile(),
        exposure_snapshot=exposure(),
        estimated_slippage_pct=0.0,
    )

    assert report.metrics["total_features"] == 3
    assert report.metrics["routed_orders"] >= 1
    assert report.metrics["blocked_orders"] >= 1
    assert len(report.trades) == 3


def test_export_and_load_paper_trading_report(tmp_path: Path):
    feature = sample_feature()
    key = price_path_key(feature)

    report = run_paper_trading_session(
        feature_snapshots=[feature],
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
        estimated_slippage_pct=0.0,
        session_name="unit_test_session",
    )

    paths = export_paper_trading_report(report, output_dir=tmp_path)

    assert paths["summary"].exists()
    assert paths["trades"].exists()

    loaded = load_paper_trading_trades(paths["trades"])

    assert len(loaded) == 1
    assert loaded[0].routed is True