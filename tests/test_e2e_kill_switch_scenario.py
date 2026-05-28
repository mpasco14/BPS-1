from e2e.e2e_kill_switch_scenario import run_e2e_kill_switch_scenario


def test_e2e_kill_switch_scenario_expected_blocked():
    report = run_e2e_kill_switch_scenario(session_name="unit_kill_switch")

    assert report.passed is True
    assert report.expected_blocked is True
    assert report.status == "EXPECTED_BLOCKED"
    assert report.components["kill_switch"]["active_after"] is True
    assert report.system_state["state"] == "KILL_SWITCH_ACTIVE"
    assert report.snapshot["healthy"] is False