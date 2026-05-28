from system_integration.portfolio_live_ops_integration import (
    LiveOpsInput,
    PortfolioRiskInput,
    integrate_portfolio_risk_live_ops,
)


def test_portfolio_live_ops_allows_clean_state():
    report = integrate_portfolio_risk_live_ops(
        portfolio=PortfolioRiskInput(concentration_status="PASS"),
        live_ops=LiveOpsInput(supervisor_allowed_to_continue=True),
    )

    assert report.allowed_to_continue is True


def test_portfolio_live_ops_blocks_kill_switch():
    report = integrate_portfolio_risk_live_ops(
        portfolio=PortfolioRiskInput(concentration_status="PASS"),
        live_ops=LiveOpsInput(kill_switch_active=True),
    )

    assert report.allowed_to_continue is False
    assert "kill_switch_active" in report.blockers