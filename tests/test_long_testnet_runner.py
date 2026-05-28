from testnet_supervision.credential_readiness import (
    TestnetCredentialReadinessConfig,
    evaluate_testnet_credential_readiness,
)
from testnet_supervision.long_testnet_runner import LongTestnetRunnerConfig, run_controlled_long_testnet_session
from testnet_supervision.supervised_session_plan import build_supervised_testnet_session_plan


def test_long_testnet_runner_simulated_passes():
    credentials = evaluate_testnet_credential_readiness(
        config=TestnetCredentialReadinessConfig(require_api_keys=False)
    )
    plan = build_supervised_testnet_session_plan(
        session_name="unit_runner",
        duration_minutes=30,
    )

    report = run_controlled_long_testnet_session(
        plan=plan,
        credential_readiness=credentials,
        config=LongTestnetRunnerConfig(simulate=True, max_loop_iterations=3),
    )

    assert report.passed is True
    assert report.simulated is True
    assert report.orders_submitted == 1
    assert report.evidence["passed"] is True