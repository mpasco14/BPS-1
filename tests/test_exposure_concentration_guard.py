from portfolio_intelligence.exposure_concentration_guard import (
    ExposureConcentrationConfig,
    evaluate_exposure_concentration,
)
from portfolio_intelligence.exposure_ledger import ExposureLedgerEvent, summarize_exposure_ledger
from portfolio_intelligence.position_lifecycle import build_position_lifecycle_report


def test_exposure_concentration_passes_small_position():
    events = [
        ExposureLedgerEvent(
            event_id="open",
            event_type="OPEN",
            symbol="BTCUSDT",
            timeframe="5m",
            side="LONG",
            notional_usd=100,
            margin_usd=5,
            leverage=5,
        )
    ]

    summary = summarize_exposure_ledger(events=events)
    lifecycle = build_position_lifecycle_report(events=events)

    report = evaluate_exposure_concentration(
        summary=summary,
        lifecycle=lifecycle,
        config=ExposureConcentrationConfig(max_total_notional_usd=1000, max_leverage=30),
    )

    assert report.passed is True


def test_exposure_concentration_blocks_total_notional():
    events = [
        ExposureLedgerEvent(
            event_id="open",
            event_type="OPEN",
            symbol="BTCUSDT",
            timeframe="5m",
            side="LONG",
            notional_usd=2000,
            margin_usd=50,
            leverage=40,
        )
    ]

    summary = summarize_exposure_ledger(events=events)

    report = evaluate_exposure_concentration(
        summary=summary,
        config=ExposureConcentrationConfig(max_total_notional_usd=1000, max_leverage=30),
    )

    assert report.passed is False
    assert "total_notional_above_limit" in report.blockers
    assert "leverage_above_limit" in report.blockers