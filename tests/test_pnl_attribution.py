from portfolio_intelligence.exposure_ledger import demo_exposure_events
from portfolio_intelligence.pnl_attribution import build_pnl_attribution_report


def test_pnl_attribution_generates_items():
    report = build_pnl_attribution_report(events=demo_exposure_events())

    assert report.items_count > 0
    assert report.total_realized_net_pnl_usd == 2.76


def test_pnl_attribution_has_timeframe_dimension():
    report = build_pnl_attribution_report(
        events=demo_exposure_events(),
        dimensions=["timeframe"],
    )

    assert report.dimensions_count == 1
    assert report.items[0]["dimension"] == "timeframe"
    assert report.items[0]["name"] == "5m"