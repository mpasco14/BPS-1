from scenario_testing.volatility_shock_scenario import run_volatility_shock_scenario


def test_volatility_shock_scenario_detects_shock():
    report = run_volatility_shock_scenario()

    assert report.passed is True
    assert report.metadata["shock_events"] > 0
    assert "volatility_shock_detected" in report.warnings