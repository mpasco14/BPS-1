from datetime import datetime, timezone

from risk.exposure import ExposureSnapshot
from risk.risk_manager import RiskProfile, approve_signal, assess_signal_risk
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


def exposure():
    return ExposureSnapshot(
        total_bankroll_usd=2000,
        daily_pnl_usd=0,
        open_positions=0,
        exposure_per_market={},
        exposure_by_timeframe={},
        btc_directional_exposure_usd=0,
    )


def sample_features(combined_score=0.9):
    direction_sign = 1 if combined_score >= 0 else -1

    return {
        "timestamp": "2026-05-15T18:00:00+00:00",
        "venue": "binance_futures",
        "instrument_id": "BTCUSDT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "tech_score": 0.9 * direction_sign,
        "microstructure_score": 0.4 * direction_sign,
        "onchain_score": 0.05 * direction_sign,
        "sentiment_score": 0.03 * direction_sign,
        "combined_score": combined_score,
        "binance_spread_pct": 0.0001,
        "binance_liquidity_usd": 100000,
        "mark_price": 60000,
        "expected_value_usd": 0.50,
        "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
    }


def signal_with_edge(features):
    signal = generate_signal(features, now=fixed_now())

    return signal.model_copy(
        update={
            "edge": 0.50 / 1.05,
            "prediction": {"expected_value_usd": 0.50},
        }
    )


def test_long_signal_reaches_risk_approval():
    features = sample_features(combined_score=0.9)
    signal = signal_with_edge(features)

    assessment = assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )

    approval = approve_signal(
        signal,
        risk_assessment=assessment,
        exposure_snapshot=exposure(),
        market_liquidity_usd=100000,
    )

    assert signal.decision == "ENTER"
    assert signal.direction == "LONG"
    assert assessment.decision == "APPROVED"
    assert approval.approved is True


def test_short_signal_reaches_risk_approval():
    features = sample_features(combined_score=-0.9)
    signal = signal_with_edge(features)

    assessment = assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )

    approval = approve_signal(
        signal,
        risk_assessment=assessment,
        exposure_snapshot=exposure(),
        market_liquidity_usd=100000,
    )

    assert signal.decision == "ENTER"
    assert signal.direction == "SHORT"
    assert assessment.decision == "APPROVED"
    assert approval.approved is True


def test_weak_signal_does_not_reach_approval():
    features = sample_features(combined_score=0.1)
    signal = signal_with_edge(features)

    assessment = assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )

    approval = approve_signal(
        signal,
        risk_assessment=assessment,
        exposure_snapshot=exposure(),
        market_liquidity_usd=100000,
    )

    assert signal.decision != "ENTER"
    assert approval.approved is False