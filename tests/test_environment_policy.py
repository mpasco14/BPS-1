from security.environment_policy import (
    EnvironmentPolicyConfig,
    EnvironmentPolicyInputs,
    evaluate_environment_policy,
)


def test_environment_policy_passes_safe_dev():
    report = evaluate_environment_policy(
        inputs=EnvironmentPolicyInputs(
            environment="development",
            execution_mode="paper",
            debug=False,
            dry_run=True,
            production_guard_enabled=True,
            kill_switch_enabled=True,
            api_keys_present=False,
        ),
        config=EnvironmentPolicyConfig(),
    )

    assert report.passed is True


def test_environment_policy_blocks_live_when_not_allowed():
    report = evaluate_environment_policy(
        inputs=EnvironmentPolicyInputs(
            environment="production",
            execution_mode="live",
            debug=False,
            dry_run=False,
            production_guard_enabled=True,
            kill_switch_enabled=True,
            live_order_adapter_enabled=True,
            live_order_submission_allowed=True,
            secrets_storage_backend="vault",
            api_keys_present=True,
        ),
        config=EnvironmentPolicyConfig(allow_live=False),
    )

    assert report.passed is False
    assert "LIVE_NOT_ALLOWED_FAILED" in report.blockers


def test_environment_policy_blocks_env_secrets_in_production():
    report = evaluate_environment_policy(
        inputs=EnvironmentPolicyInputs(
            environment="production",
            execution_mode="paper",
            debug=False,
            dry_run=True,
            production_guard_enabled=True,
            kill_switch_enabled=True,
            secrets_storage_backend="env",
            api_keys_present=True,
        ),
        config=EnvironmentPolicyConfig(forbid_env_secrets_in_production=True),
    )

    assert report.passed is False
    assert "ENV_SECRETS_FORBIDDEN_IN_PRODUCTION_FAILED" in report.blockers