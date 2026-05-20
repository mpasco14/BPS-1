from ops.live_preflight import (
    LivePreflightConfig,
    LivePreflightInputs,
    build_live_preflight_report,
    export_live_preflight_report,
)


def good_inputs():
    return LivePreflightInputs(
        live_safety_passed=True,
        capital_ramp_passed=True,
        deployment_readiness_passed=True,
        testnet_warmup_passed=True,
        testnet_continuous_passed=True,
        emergency_safe_mode_active=False,
        risk_state_status="OK",
        risk_state_blockers=[],
        binance_allow_live_trading=False,
        risk_allow_live_trading=False,
        binance_execution_mode="paper",
    )


def test_live_preflight_passes_with_good_inputs():
    report = build_live_preflight_report(
        inputs=good_inputs(),
        config=LivePreflightConfig(require_testnet_continuous_pass=False),
    )

    assert report.passed is True


def test_live_preflight_fails_if_live_flags_enabled():
    inputs = good_inputs()
    inputs.binance_allow_live_trading = True

    report = build_live_preflight_report(
        inputs=inputs,
        config=LivePreflightConfig(require_testnet_continuous_pass=False),
    )

    assert report.passed is False
    assert any(check["code"] == "LIVE_FLAGS_ENABLED_DURING_PREFLIGHT" for check in report.checks)


def test_export_live_preflight_report(tmp_path):
    report = build_live_preflight_report(
        inputs=good_inputs(),
        config=LivePreflightConfig(require_testnet_continuous_pass=False),
    )

    path = export_live_preflight_report(
        report,
        output_dir=tmp_path,
        name="unit_preflight",
    )

    assert path.exists()