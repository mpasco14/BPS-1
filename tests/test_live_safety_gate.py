from ops.live_safety_gate import (
    LiveSafetyConfig,
    LiveSafetyInputs,
    build_live_safety_report,
    export_live_safety_report,
)


def good_inputs():
    return LiveSafetyInputs(
        security_passed=True,
        compliance_blocking_fail_count=0,
        runbook_passed=True,
        deployment_readiness_passed=True,
        testnet_warmup_passed=True,
        emergency_safe_mode_active=False,
        legal_review_approved=True,
        binance_allow_live_trading=False,
        risk_allow_live_trading=False,
        binance_execution_mode="paper",
    )


def test_live_safety_passes_with_good_inputs():
    report = build_live_safety_report(
        inputs=good_inputs(),
        config=LiveSafetyConfig(),
    )

    assert report.passed is True
    assert report.live_allowed_by_gate is True
    assert report.auto_enable_live_allowed is False


def test_live_safety_fails_without_legal_review():
    inputs = good_inputs()
    inputs.legal_review_approved = False

    report = build_live_safety_report(
        inputs=inputs,
        config=LiveSafetyConfig(),
    )

    assert report.passed is False
    assert any(check["code"] == "LEGAL_REVIEW_REQUIRED" for check in report.checks)


def test_live_safety_fails_if_live_already_enabled():
    inputs = good_inputs()
    inputs.binance_allow_live_trading = True

    report = build_live_safety_report(
        inputs=inputs,
        config=LiveSafetyConfig(),
    )

    assert report.passed is False
    assert any(check["code"] == "LIVE_ENABLED_DURING_SAFETY_CHECK" for check in report.checks)


def test_export_live_safety_report(tmp_path):
    report = build_live_safety_report(
        inputs=good_inputs(),
        config=LiveSafetyConfig(),
    )

    path = export_live_safety_report(
        report,
        output_dir=tmp_path,
        name="unit_live_safety",
    )

    assert path.exists()