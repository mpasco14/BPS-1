from datetime import datetime, timezone

from execution.binance_futures_client import BinanceFuturesConfig, BinanceFuturesRestClient
from execution.limit_order import rules_from_symbol_info
from execution.order_router import InMemoryOrderRegistry, route_signal_to_order
from risk.exposure import ExposureSnapshot
from risk.risk_manager import RiskProfile
from strategy.signal_engine import generate_signal


def fixed_now():
    return datetime(2026, 5, 15, 18, 1, 0, tzinfo=timezone.utc)


def sample_signal(**overrides):
    features = {
        "timestamp": "2026-05-15T18:00:00+00:00",
        "venue": "binance_futures",
        "instrument_id": "BTCUSDT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "tech_score": 0.9,
        "microstructure_score": 0.4,
        "onchain_score": 0.05,
        "sentiment_score": 0.03,
        "combined_score": 0.9,
        "binance_spread_pct": 0.0001,
        "binance_liquidity_usd": 100000,
        "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
    }

    features.update(overrides)

    signal = generate_signal(features, now=fixed_now())

    return signal.model_copy(update={"edge": 0.50 / 1.05})


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


def paper_client():
    config = BinanceFuturesConfig(execution_mode="paper")
    return BinanceFuturesRestClient(config=config)


def test_route_valid_signal_to_paper_order():
    registry = InMemoryOrderRegistry()

    result = route_signal_to_order(
        signal=sample_signal(),
        entry_price=60000,
        rules=symbol_rules(),
        client=paper_client(),
        profile=custom_profile(),
        exposure_snapshot=exposure(),
        market_liquidity_usd=100000,
        registry=registry,
    )

    assert result.decision == "ROUTED"
    assert result.record["status"] == "PAPER_ACCEPTED"
    assert result.record["order_payload"]["symbol"] == "BTCUSDT"
    assert registry.count() == 1


def test_route_blocks_hold_signal():
    result = route_signal_to_order(
        signal=sample_signal(combined_score=0.1),
        entry_price=60000,
        rules=symbol_rules(),
        client=paper_client(),
        profile=custom_profile(),
        exposure_snapshot=exposure(),
    )

    assert result.decision == "BLOCKED"
    assert "signal_not_enter" in result.record["blockers"]


def test_route_blocks_kill_switch():
    result = route_signal_to_order(
        signal=sample_signal(),
        entry_price=60000,
        rules=symbol_rules(),
        client=paper_client(),
        profile=custom_profile(),
        exposure_snapshot=exposure(),
        kill_switch_input={"ws_disconnected_seconds": 31},
    )

    assert result.decision == "BLOCKED"
    assert result.record["status"] == "KILL_SWITCH_ACTIVE"