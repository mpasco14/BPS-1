from infra.failure_injection import (
    FailureScenario,
    build_failure_injection_report,
    demo_failure_scenarios,
    evaluate_failure_scenario,
)


def test_failure_scenario_passes_expected_actions():
    result = evaluate_failure_scenario(
        FailureScenario(
            scenario_id="redis_down",
            failure_type="REDIS_DOWN",
            observed_actions=["use_local_fallback", "do_not_open_new_large_positions", "emit_alert"],
        )
    )

    assert result.passed is True
    assert result.status == "PASS"


def test_failure_scenario_blocks_unsafe_action():
    result = evaluate_failure_scenario(
        FailureScenario(
            scenario_id="bad",
            failure_type="MODEL_NAN",
            observed_actions=["submit_live_order"],
        )
    )

    assert result.passed is False
    assert "submit_live_order" in result.unsafe_actions


def test_failure_injection_report_demo():
    report = build_failure_injection_report(scenarios=demo_failure_scenarios())

    assert report.passed is True
    assert report.scenarios_count == 3