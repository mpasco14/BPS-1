from testnet_supervision.credential_readiness import (
    TestnetCredentialReadinessConfig,
    evaluate_testnet_credential_readiness,
)
from testnet_supervision.supervised_session_plan import (
    build_supervised_testnet_session_plan,
    evaluate_supervised_testnet_session_plan,
)


def test_supervised_session_plan_passes_demo():
    credentials = evaluate_testnet_credential_readiness(
        config=TestnetCredentialReadinessConfig(require_api_keys=False)
    )
    plan = build_supervised_testnet_session_plan(
        session_name="unit_supervised",
        duration_minutes=30,
    )

    report = evaluate_supervised_testnet_session_plan(
        plan=plan,
        credential_readiness=credentials,
    )

    assert report.passed is True


def test_supervised_session_plan_blocks_invalid_duration():
    credentials = evaluate_testnet_credential_readiness(
        config=TestnetCredentialReadinessConfig(require_api_keys=False)
    )
    plan = build_supervised_testnet_session_plan(
        session_name="unit_invalid",
        duration_minutes=30,
    )
    plan.duration_minutes = 0

    report = evaluate_supervised_testnet_session_plan(
        plan=plan,
        credential_readiness=credentials,
    )

    assert report.passed is False
    assert "duration_minutes_must_be_positive" in report.blockers