from scenario_testing.scenario_testing_report import run_all_scenario_tests


def test_run_all_scenario_tests_passes():
    report = run_all_scenario_tests(export=False)

    assert report.passed is True
    assert report.scenarios_count == 5
    assert report.fail_count == 0