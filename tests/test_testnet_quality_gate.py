from ops.testnet_quality_gate import TestnetQualityConfig, evaluate_testnet_quality
from ops.testnet_session import TestnetOrderEvent, build_testnet_session_report


def good_report():
    events = [
        TestnetOrderEvent(
            side="BUY",
            quantity=0.01,
            requested_price=60000,
            executed_price=60001,
            status="FILLED",
            latency_ms=100,
            estimated_slippage_pct=0.0005,
            realized_slippage_pct=0.0004,
            pnl_usd=1,
        ),
        TestnetOrderEvent(
            side="SELL",
            quantity=0.01,
            requested_price=60100,
            executed_price=60099,
            status="FILLED",
            latency_ms=110,
            estimated_slippage_pct=0.0005,
            realized_slippage_pct=0.0004,
            pnl_usd=1,
        ),
    ]

    return build_testnet_session_report(
        events=events,
        session_name="quality_unit",
    )


def test_quality_gate_passes_good_report():
    quality = evaluate_testnet_quality(
        report=good_report(),
        config=TestnetQualityConfig(),
    )

    assert quality.passed is True


def test_quality_gate_fails_low_fill_rate():
    events = [
        TestnetOrderEvent(
            side="BUY",
            quantity=0.01,
            status="REJECTED",
        )
    ]

    report = build_testnet_session_report(
        events=events,
        session_name="bad_quality",
    )

    quality = evaluate_testnet_quality(
        report=report,
        config=TestnetQualityConfig(),
    )

    assert quality.passed is False
    assert any(check["code"] == "FILL_RATE_LOW" for check in quality.checks)