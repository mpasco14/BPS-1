import pytest

from datetime import datetime, timezone

from strategy.signal_engine import generate_signal

from risk.risk_manager import (
    AccountRiskState,
    RiskProfile,
    assess_signal_risk,
    calculate_order_plan,
    get_default_risk_profile,
    should_forward_to_executor,
)


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

    return generate_signal(features, now=fixed_now())


def custom_profile(**overrides):
    data = {
        "venue": "binance_futures",
        "symbol": "BTCUSDT",
        "margin_usd": 20,
        "leverage": 30,
        "notional_usd": 600,
        "gross_take_profit_usd": 2.10,
        "gross_stop_loss_usd": 1.05,
        "estimated_entry_fee_usd": 0.05,
        "estimated_exit_fee_usd": 0.05,
        "max_leverage": 30,
        "max_margin_usd": 20,
        "max_notional_usd": 600,
        "max_daily_loss_usd": 5,
        "max_trade_loss_usd": 1.05,
        "max_consecutive_losses": 3,
        "max_open_positions": 1,
        "max_open_orders": 3,
        "max_spread_pct": 0.002,
        "min_liquidity_usd": 50000,
        "min_confidence": 0.65,
    }

    data.update(overrides)

    return RiskProfile(**data)


def test_get_default_risk_profile():
    profile = get_default_risk_profile()

    assert profile.venue == "binance_futures"
    assert profile.symbol == "BTCUSDT"
    assert profile.margin_usd == 20
    assert profile.leverage == 30
    assert profile.notional_usd == 600


def test_calculate_long_order_plan():
    plan = calculate_order_plan(
        direction="LONG",
        entry_price=60000,
        timeframe="5m",
        profile=custom_profile(),
    )

    assert plan.order_side == "BUY"
    assert plan.quantity == pytest.approx(0.01)
    assert plan.take_profit_price == pytest.approx(60210)
    assert plan.stop_loss_price == pytest.approx(59895)
    assert plan.expected_net_profit_usd == pytest.approx(2.0)
    assert plan.risk_reward_ratio == pytest.approx(2.0)


def test_calculate_short_order_plan():
    plan = calculate_order_plan(
        direction="SHORT",
        entry_price=60000,
        timeframe="5m",
        profile=custom_profile(),
    )

    assert plan.order_side == "SELL"
    assert plan.take_profit_price == pytest.approx(59790)
    assert plan.stop_loss_price == pytest.approx(60105)


def test_approves_valid_signal():
    assessment = assess_signal_risk(
        signal=sample_signal(),
        entry_price=60000,
        profile=custom_profile(),
    )

    assert assessment.decision == "APPROVED"
    assert assessment.blockers == []
    assert assessment.order_plan is not None
    assert should_forward_to_executor(assessment) is True


def test_blocks_non_enter_signal():
    assessment = assess_signal_risk(
        signal=sample_signal(combined_score=0.1),
        entry_price=60000,
        profile=custom_profile(),
    )

    assert assessment.decision == "BLOCKED"
    assert "signal_not_enter" in assessment.blockers


def test_blocks_kill_switch():
    assessment = assess_signal_risk(
        signal=sample_signal(),
        entry_price=60000,
        account_state=AccountRiskState(kill_switch_active=True),
        profile=custom_profile(),
    )

    assert assessment.decision == "BLOCKED"
    assert "kill_switch_active" in assessment.blockers


def test_blocks_daily_loss():
    assessment = assess_signal_risk(
        signal=sample_signal(),
        entry_price=60000,
        account_state=AccountRiskState(daily_pnl_usd=-5),
        profile=custom_profile(),
    )

    assert assessment.decision == "BLOCKED"
    assert "max_daily_loss_reached" in assessment.blockers


def test_blocks_open_position_limit():
    assessment = assess_signal_risk(
        signal=sample_signal(),
        entry_price=60000,
        account_state=AccountRiskState(open_positions=1),
        profile=custom_profile(),
    )

    assert assessment.decision == "BLOCKED"
    assert "max_open_positions_reached" in assessment.blockers