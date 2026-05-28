from scenario_testing.chop_sideways_scenario import run_chop_sideways_scenario


def test_chop_sideways_scenario_limits_overtrading():
    report = run_chop_sideways_scenario()

    assert report.passed is True
    assert report.metadata["signal_ratio"] <= report.metadata["max_signal_ratio"]