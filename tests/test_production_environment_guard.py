from ops.production_environment_guard import (
    ProductionEnvironmentGuardConfig,
    ProductionEnvironmentInputs,
    evaluate_production_environment_guard,
)


def test_production_guard_passes_with_all_gates():
    report = evaluate_production_environment_guard(
        inputs=ProductionEnvironmentInputs(
            testnet_passed=True,
            live_preflight_passed=True,
            live_risk_audit_passed=True,
            capital_ramp_validated=True,
            secrets_audit_passed=True,
            human_approval_valid=True,
            emergency_state_clear=True,
        ),
        config=ProductionEnvironmentGuardConfig(),
    )

    assert report.passed is True


def test_production_guard_blocks_missing_human_approval():
    report = evaluate_production_environment_guard(
        inputs=ProductionEnvironmentInputs(
            testnet_passed=True,
            live_preflight_passed=True,
            live_risk_audit_passed=True,
            capital_ramp_validated=True,
            secrets_audit_passed=True,
            human_approval_valid=False,
            emergency_state_clear=True,
        ),
        config=ProductionEnvironmentGuardConfig(),
    )

    assert report.passed is False
    assert "HUMAN_APPROVAL_VALID_FAILED" in report.blockers