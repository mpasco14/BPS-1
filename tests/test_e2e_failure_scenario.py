from e2e.e2e_failure_scenario import run_e2e_failure_scenario


def test_e2e_failure_scenario_expected_blocked():
    report = run_e2e_failure_scenario(
        session_name="unit_failure",
        failure_mode="low_confidence_signal",
    )

    assert report.passed is True
    assert report.expected_blocked is True
    assert report.status == "EXPECTED_BLOCKED"
    assert "signal_confidence_below_minimum" in report.blockers
    assert report.snapshot["healthy"] is False


def test_e2e_failure_scenario_risk_rejected():
    report = run_e2e_failure_scenario(
        session_name="unit_failure_risk",
        failure_mode="risk_rejected",
    )

    assert report.passed is True
    assert report.expected_blocked is True
    assert any("risk" in item for item in report.blockers)