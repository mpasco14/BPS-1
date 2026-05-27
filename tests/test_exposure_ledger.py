from portfolio_intelligence.exposure_ledger import (
    ExposureLedgerEvent,
    build_exposure_ledger,
    demo_exposure_events,
    summarize_exposure_ledger,
)


def test_exposure_ledger_summary_closed_position_net_pnl():
    events = demo_exposure_events()
    ledger = build_exposure_ledger(events=events)
    summary = summarize_exposure_ledger(ledger=ledger)

    assert summary.events_count == 3
    assert summary.total_abs_notional_usd == 0
    assert summary.realized_pnl_usd == 3.0
    assert summary.fees_usd == 0.24
    assert summary.realized_net_pnl_usd == 2.76


def test_exposure_ledger_open_position_exposure():
    events = [
        ExposureLedgerEvent(
            event_id="open",
            event_type="OPEN",
            symbol="BTCUSDT",
            timeframe="5m",
            side="LONG",
            notional_usd=600,
            margin_usd=20,
            leverage=30,
        )
    ]

    summary = summarize_exposure_ledger(events=events)

    assert summary.total_abs_notional_usd == 600
    assert summary.net_notional_usd == 600
    assert summary.total_margin_usd == 20