from datetime import datetime, timezone

from risk.exposure import ExposureSnapshot
from risk.kill_switch import evaluate_kill_switch
from risk.risk_manager import RiskProfile, approve_signal, assess_signal_risk
from risk.sizing import calculate_fractional_kelly_position
from strategy.signal_engine import generate_signal


def fixed_now():
    return datetime(2026, 5, 15, 18, 1, 0, tzinfo=timezone.utc)


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


def sample_signal():
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
        "mark_price": 60000,
        "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
    }

    signal = generate_signal(features, now=fixed_now())

    return signal.model_copy(
        update={
            "edge": 0.50 / 1.05,
            "prediction": {"expected_value_usd": 0.50},
        }
    )


def exposure(
    *,
    bankroll=2000,
    daily_pnl=0,
    market_exposure=None,
    timeframe_exposure=None,
    btc_directional_exposure=0,
):
    return ExposureSnapshot(
        total_bankroll_usd=bankroll,
        daily_pnl_usd=daily_pnl,
        open_positions=0,
        exposure_per_market=market_exposure or {},
        exposure_by_timeframe=timeframe_exposure or {},
        btc_directional_exposure_usd=btc_directional_exposure,
    )


def approval_for_snapshot(snapshot):
    signal = sample_signal()

    assessment = assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )

    return approve_signal(
        signal,
        risk_assessment=assessment,
        exposure_snapshot=snapshot,
        market_liquidity_usd=100000,
    )


def test_trade_above_bankroll_risk_is_rejected():
    result = approval_for_snapshot(
        exposure(bankroll=100)
    )

    assert result.approved is False
    assert "trade_risk_above_limit" in result.blockers


def test_daily_drawdown_blocks_new_trade():
    result = approval_for_snapshot(
        exposure(bankroll=2000, daily_pnl=-60)
    )

    assert result.approved is False
    assert "daily_loss_limit_reached" in result.blockers


def test_btc_directional_exposure_blocks_new_position():
    result = approval_for_snapshot(
        exposure(bankroll=2000, btc_directional_exposure=200)
    )

    assert result.approved is False
    assert "btc_directional_exposure_above_limit" in result.blockers


def test_fractional_kelly_never_exceeds_bankroll_cap():
    plan = calculate_fractional_kelly_position(
        bankroll_usd=2000,
        edge=10,
        odds=1,
        market_liquidity_usd=1_000_000,
        reduction_factor=0.25,
        max_bankroll_pct=0.005,
    )

    assert plan.final_position_usd <= 10


def test_kill_switch_activates_on_model_ood():
    state = evaluate_kill_switch({"model_ood": True})

    assert state.active is True
    assert "model_out_of_distribution" in state.triggers
    assert state.cancel_open_orders is True