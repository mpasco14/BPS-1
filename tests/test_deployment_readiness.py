from ops.deployment_readiness import (
    DeploymentReadinessConfig,
    DeploymentReadinessInputs,
    build_deployment_readiness_report,
    export_deployment_readiness_report,
)


def good_inputs():
    return DeploymentReadinessInputs(
        security_passed=True,
        compliance_passed=True,
        compliance_blocking_fail_count=0,
        runbook_passed=True,
        testnet_warmup_passed=True,
        emergency_safe_mode_active=False,
        binance_allow_live_trading=False,
        risk_allow_live_trading=False,
        binance_execution_mode="paper",
        legal_review_approved=True,
    )


def test_testnet_readiness_passes_with_good_inputs():
    report = build_deployment_readiness_report(
        stage="testnet",
        inputs=good_inputs(),
        config=DeploymentReadinessConfig(),
    )

    assert report.passed is True
    assert report.live_allowed_by_gate is False


def test_live_readiness_passes_only_with_all_requirements():
    report = build_deployment_readiness_report(
        stage="live",
        inputs=good_inputs(),
        config=DeploymentReadinessConfig(),
    )

    assert report.passed is True
    assert report.live_allowed_by_gate is True


def test_live_readiness_fails_without_legal_review():
    inputs = good_inputs()
    inputs.legal_review_approved = False

    report = build_deployment_readiness_report(
        stage="live",
        inputs=inputs,
        config=DeploymentReadinessConfig(),
    )

    assert report.passed is False
    assert any(check["code"] == "LEGAL_REVIEW_REQUIRED_FOR_LIVE" for check in report.checks)


def test_readiness_fails_when_emergency_state_active():
    inputs = good_inputs()
    inputs.emergency_safe_mode_active = True

    report = build_deployment_readiness_report(
        stage="testnet",
        inputs=inputs,
        config=DeploymentReadinessConfig(),
    )

    assert report.passed is False
    assert any(check["code"] == "EMERGENCY_STATE_ACTIVE" for check in report.checks)


def test_export_deployment_readiness_report(tmp_path):
    report = build_deployment_readiness_report(
        stage="testnet",
        inputs=good_inputs(),
        config=DeploymentReadinessConfig(),
    )

    path = export_deployment_readiness_report(
        report,
        output_dir=tmp_path,
        name="unit_readiness",
    )

    assert path.exists()