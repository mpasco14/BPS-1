from e2e.e2e_full_system_report import build_e2e_full_system_report, run_all_e2e_scenarios
from e2e.e2e_models import E2EScenarioReport


def test_e2e_full_system_report_aggregates_scenarios():
    report = build_e2e_full_system_report(
        scenarios=[
            E2EScenarioReport(
                scenario_name="paper",
                scenario_kind="paper_trading",
                status="PASS",
                passed=True,
            ),
            E2EScenarioReport(
                scenario_name="failure",
                scenario_kind="failure",
                status="EXPECTED_BLOCKED",
                passed=True,
                expected_blocked=True,
            ),
        ]
    )

    assert report.passed is True
    assert report.scenarios_count == 2
    assert report.pass_count == 1
    assert report.expected_blocked_count == 1


def test_run_all_e2e_scenarios_passes():
    report = run_all_e2e_scenarios(session_name="unit_e2e_all", export=False)

    assert report.passed is True
    assert report.scenarios_count == 4
    assert report.expected_blocked_count == 2