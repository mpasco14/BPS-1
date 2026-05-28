from e2e.e2e_paper_trading import run_e2e_paper_trading_scenario


def test_e2e_paper_trading_scenario_passes():
    report = run_e2e_paper_trading_scenario(session_name="unit_paper")

    assert report.passed is True
    assert report.scenario_kind == "paper_trading"
    assert report.snapshot["healthy"] is True
    assert report.components["signal_pipeline"]["approved"] is True