from portfolio_intelligence.exposure_ledger import ExposureLedgerEvent, demo_exposure_events
from portfolio_intelligence.position_lifecycle import build_position_lifecycle_report


def test_position_lifecycle_closed_demo():
    report = build_position_lifecycle_report(events=demo_exposure_events())

    assert report.positions_count == 1
    assert report.closed_positions_count == 1
    assert report.open_positions_count == 0


def test_position_lifecycle_open_position():
    report = build_position_lifecycle_report(
        events=[
            ExposureLedgerEvent(
                event_id="open",
                event_type="OPEN",
                position_id="pos",
                symbol="BTCUSDT",
                timeframe="5m",
                side="LONG",
                quantity=0.01,
                notional_usd=600,
            )
        ]
    )

    assert report.positions_count == 1
    assert report.open_positions_count == 1