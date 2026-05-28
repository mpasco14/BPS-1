from testnet_supervision.credential_readiness import (
    TestnetCredentialReadinessConfig,
    evaluate_testnet_credential_readiness,
)
from testnet_supervision.long_testnet_runner import LongTestnetRunnerConfig, run_controlled_long_testnet_session
from testnet_supervision.session_review_gate import review_testnet_session_for_promotion
from testnet_supervision.supervised_session_plan import (
    build_supervised_testnet_session_plan,
    evaluate_supervised_testnet_session_plan,
)


def test_session_review_gate_approves_longer_testnet():
    credentials = evaluate_testnet_credential_readiness(
        config=TestnetCredentialReadinessConfig(require_api_keys=False)
    )
    plan = build_supervised_testnet_session_plan(
        session_name="unit_review",
        duration_minutes=30,
    )
    plan_report = evaluate_supervised_testnet_session_plan(
        plan=plan,
        credential_readiness=credentials,
    )
    runner = run_controlled_long_testnet_session(
        plan=plan,
        credential_readiness=credentials,
        config=LongTestnetRunnerConfig(simulate=True),
    )

    report = review_testnet_session_for_promotion(
        credential_readiness=credentials,
        session_plan=plan_report,
        runner=runner,
        evidence=runner.evidence,
    )

    assert report.passed is True
    assert report.decision == "APPROVED_FOR_LONGER_TESTNET"


def test_session_review_gate_blocks_failed_runner():
    credentials = evaluate_testnet_credential_readiness(
        config=TestnetCredentialReadinessConfig(require_api_keys=False)
    )
    plan = build_supervised_testnet_session_plan(
        session_name="unit_review_failed",
        duration_minutes=30,
    )
    plan_report = evaluate_supervised_testnet_session_plan(
        plan=plan,
        credential_readiness=credentials,
    )
    runner = run_controlled_long_testnet_session(
        plan=plan,
        credential_readiness=credentials,
        config=LongTestnetRunnerConfig(simulate=True),
    )
    runner.passed = False
    runner.blockers.append("unit_forced_failure")

    report = review_testnet_session_for_promotion(
        credential_readiness=credentials,
        session_plan=plan_report,
        runner=runner,
        evidence=runner.evidence,
    )

    assert report.passed is False
    assert report.decision == "FIX_REQUIRED"