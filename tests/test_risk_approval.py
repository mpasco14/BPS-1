from datetime import datetime, timezone
from risk.exposure import ExposureSnapshot
from risk.risk_manager import RiskProfile, approve, approve_signal, assess_signal_risk
from strategy.signal_engine import generate_signal


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
        "prediction": {
            "expected_value_usd": 0.50,
        },
    }

    features.update(overrides)
    signal = generate_signal(features, now=fixed_now())

    # injeta prediction como campo extra aceito pelo Pydantic
    return signal.model_copy(
    update={
        "prediction": features["prediction"],
        "edge": 0.50 / 1.05,
    }
)


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

def fixed_now():
    return datetime(2026, 5, 15, 18, 1, 0, tzinfo=timezone.utc)

def test_approve_valid_signal():
    signal = sample_signal()
    assessment = assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )

    result = approve_signal(
        signal,
        risk_assessment=assessment,
        exposure_snapshot=exposure(),
        market_liquidity_usd=100000,
    )

    assert result.approved is True
    assert result.blockers == []
    assert approve(
        signal,
        risk_assessment=assessment,
        exposure_snapshot=exposure(),
        market_liquidity_usd=100000,
    ) is True


def test_blocks_daily_loss_limit():
    signal = sample_signal()
    assessment = assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )

    snapshot = exposure()
    snapshot.daily_pnl_usd = -60

    result = approve_signal(
        signal,
        risk_assessment=assessment,
        exposure_snapshot=snapshot,
    )

    assert result.approved is False
    assert "daily_loss_limit_reached" in result.blockers


def test_blocks_market_exposure_limit():
    signal = sample_signal()
    assessment = assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )

    snapshot = exposure()
    snapshot.exposure_per_market = {"BTCUSDT": 100}

    result = approve_signal(
        signal,
        risk_assessment=assessment,
        exposure_snapshot=snapshot,
    )

    assert result.approved is False
    assert "market_exposure_above_limit" in result.blockers


def test_blocks_timeframe_exposure_limit():
    signal = sample_signal()
    assessment = assess_signal_risk(
        signal=signal,
        entry_price=60000,
        profile=custom_profile(),
    )

    snapshot = exposure()
    snapshot.exposure_by_timeframe = {"5m": 40}

    result = approve_signal(
        signal,
        risk_assessment=assessment,
        exposure_snapshot=snapshot,
    )

    assert result.approved is False
    assert "timeframe_exposure_above_limit" in result.blockers