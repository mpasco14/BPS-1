from testnet_readiness.testnet_session_plan import build_testnet_session_plan, evaluate_testnet_session_plan


def test_testnet_session_plan_passes_when_prereqs_pass():
    report = evaluate_testnet_session_plan(
        plan=build_testnet_session_plan(
            e2e_passed=True,
            scenario_testing_passed=True,
            kill_switch_test_passed=True,
        )
    )

    assert report.passed is True


def test_testnet_session_plan_blocks_missing_e2e():
    report = evaluate_testnet_session_plan(
        plan=build_testnet_session_plan(
            e2e_passed=False,
            scenario_testing_passed=True,
            kill_switch_test_passed=True,
        )
    )

    assert report.passed is False
    assert "e2e_not_passed" in report.blockers