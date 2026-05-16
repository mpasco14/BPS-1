from datetime import datetime, timezone

from strategy.signal_engine import (
    FeatureInput,
    calculate_confidence,
    generate_signal,
    get_threshold_for_timeframe,
    infer_direction,
    normalize_timeframe,
    should_forward_to_risk_manager,
    signal_to_dict,
)


def sample_features(**overrides):
    data = {
        "timestamp": "2026-05-15T18:00:00+00:00",
        "venue": "binance_futures",
        "instrument_id": "BTCUSDT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "tech_score": 0.8,
        "microstructure_score": 0.5,
        "onchain_score": 0.05,
        "sentiment_score": 0.03,
        "combined_score": 0.8,
        "binance_spread_pct": 0.0001,
        "binance_liquidity_usd": 100000,
        "btc_features": {
            "orderbook": {
                "is_tradeable": True,
                "blockers": [],
            }
        },
        "raw_components": {},
    }

    data.update(overrides)

    return data


def fixed_now():
    return datetime(2026, 5, 15, 18, 1, 0, tzinfo=timezone.utc)


def test_normalize_timeframe():
    assert normalize_timeframe("5M") == "5m"
    assert normalize_timeframe("15m") == "15m"
    assert normalize_timeframe("1H") == "1h"
    assert normalize_timeframe("1D") == "1d"


def test_get_threshold_for_timeframe():
    assert get_threshold_for_timeframe("5m") == 0.35
    assert get_threshold_for_timeframe("15m") == 0.30
    assert get_threshold_for_timeframe("1h") == 0.25
    assert get_threshold_for_timeframe("1d") == 0.20


def test_infer_direction_long():
    assert infer_direction(combined_score=0.5, threshold=0.35) == "LONG"


def test_infer_direction_short():
    assert infer_direction(combined_score=-0.5, threshold=0.35) == "SHORT"


def test_infer_direction_hold():
    assert infer_direction(combined_score=0.1, threshold=0.35) == "HOLD"


def test_calculate_confidence():
    confidence = calculate_confidence(
        combined_score=0.8,
        threshold=0.35,
    )

    assert 0 <= confidence <= 1
    assert confidence > 0


def test_feature_input_normalizes_symbol_and_timeframe():
    features = FeatureInput.model_validate(
        sample_features(symbol="btcusdt", instrument_id="btcusdt", timeframe="5M")
    )

    assert features.symbol == "BTCUSDT"
    assert features.instrument_id == "BTCUSDT"
    assert features.timeframe == "5m"


def test_generate_long_enter_signal():
    signal = generate_signal(
        sample_features(combined_score=0.9, microstructure_score=0.3),
        now=fixed_now(),
    )

    assert signal.direction == "LONG"
    assert signal.decision == "ENTER"
    assert signal.blockers == []
    assert should_forward_to_risk_manager(signal) is True


def test_generate_short_enter_signal():
    signal = generate_signal(
        sample_features(
            combined_score=-0.9,
            tech_score=-0.8,
            microstructure_score=-0.3,
            onchain_score=-0.05,
            sentiment_score=-0.02,
        ),
        now=fixed_now(),
    )

    assert signal.direction == "SHORT"
    assert signal.decision == "ENTER"
    assert signal.blockers == []
    assert should_forward_to_risk_manager(signal) is True


def test_generate_hold_no_trade_signal():
    signal = generate_signal(
        sample_features(combined_score=0.1),
        now=fixed_now(),
    )

    assert signal.direction == "HOLD"
    assert signal.decision == "NO_TRADE"
    assert should_forward_to_risk_manager(signal) is False


def test_blocks_stale_features():
    signal = generate_signal(
        sample_features(timestamp="2026-05-15T17:00:00+00:00"),
        now=fixed_now(),
    )

    assert signal.decision == "BLOCKED"
    assert "feature_snapshot_stale" in signal.blockers


def test_blocks_wide_spread():
    signal = generate_signal(
        sample_features(binance_spread_pct=0.01),
        now=fixed_now(),
    )

    assert signal.decision == "BLOCKED"
    assert "spread_too_wide" in signal.blockers


def test_blocks_low_liquidity():
    signal = generate_signal(
        sample_features(binance_liquidity_usd=10),
        now=fixed_now(),
    )

    assert signal.decision == "BLOCKED"
    assert "insufficient_liquidity" in signal.blockers


def test_blocks_non_tradeable_orderbook():
    features = sample_features(
        btc_features={
            "orderbook": {
                "is_tradeable": False,
                "blockers": ["liquidity_gap_too_large"],
            }
        }
    )

    signal = generate_signal(features, now=fixed_now())

    assert signal.decision == "BLOCKED"
    assert "orderbook_not_tradeable" in signal.blockers
    assert "orderbook_liquidity_gap_too_large" in signal.blockers


def test_blocks_microstructure_contradiction_long():
    signal = generate_signal(
        sample_features(combined_score=0.9, microstructure_score=-0.5),
        now=fixed_now(),
    )

    assert signal.direction == "LONG"
    assert signal.decision == "BLOCKED"
    assert "microstructure_contradicts_long" in signal.blockers


def test_blocks_microstructure_contradiction_short():
    signal = generate_signal(
        sample_features(
            combined_score=-0.9,
            tech_score=-0.8,
            microstructure_score=0.5,
        ),
        now=fixed_now(),
    )

    assert signal.direction == "SHORT"
    assert signal.decision == "BLOCKED"
    assert "microstructure_contradicts_short" in signal.blockers


def test_signal_to_dict():
    signal = generate_signal(
        sample_features(combined_score=0.9, microstructure_score=0.3),
        now=fixed_now(),
    )

    payload = signal_to_dict(signal)

    assert payload["source"] == "signal_engine"
    assert payload["direction"] == "LONG"
    assert payload["decision"] == "ENTER"