from portfolio_intelligence.exposure_concentration_guard import evaluate_exposure_concentration
from portfolio_intelligence.exposure_ledger import build_exposure_ledger, demo_exposure_events, summarize_exposure_ledger
from portfolio_intelligence.pnl_attribution import build_pnl_attribution_report
from portfolio_intelligence.portfolio_risk_dashboard import build_portfolio_risk_dashboard
from portfolio_intelligence.position_lifecycle import build_position_lifecycle_report


def test_portfolio_risk_dashboard_demo():
    events = demo_exposure_events()
    ledger = build_exposure_ledger(events=events)
    summary = summarize_exposure_ledger(ledger=ledger)
    lifecycle = build_position_lifecycle_report(events=events)
    concentration = evaluate_exposure_concentration(summary=summary, lifecycle=lifecycle)
    pnl = build_pnl_attribution_report(events=events)

    dashboard = build_portfolio_risk_dashboard(
        summary=summary,
        lifecycle=lifecycle,
        concentration=concentration,
        pnl_attribution=pnl,
    )

    assert dashboard.passed is True
    assert dashboard.headline["realized_net_pnl_usd"] == 2.76