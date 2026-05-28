from scenario_testing.trend_regime_scenario import run_trend_regime_scenario


def test_trend_regime_uptrend_passes():
    report = run_trend_regime_scenario(trend_direction="uptrend")

    assert report.passed is True
    assert report.metadata["directional_signal_ratio"] >= report.metadata["min_directional_signal_ratio"]


def test_trend_regime_downtrend_passes():
    report = run_trend_regime_scenario(trend_direction="downtrend")

    assert report.passed is True
    assert report.metadata["directional_signal_ratio"] >= report.metadata["min_directional_signal_ratio"]