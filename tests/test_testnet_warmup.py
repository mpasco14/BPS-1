from ops.testnet_warmup import (
    TestnetWarmupConfig,
    TestnetWarmupInputs,
    build_testnet_warmup_report,
    export_testnet_warmup_report,
)


def good_inputs():
    return TestnetWarmupInputs(
        days_completed=14,
        trades_count=50,
        fill_rate=0.75,
        average_slippage_error_pct=0.0005,
        critical_alerts=0,
        warning_alerts=1,
        ops_check_passed=True,
        runbook_passed=True,
    )


def test_good_warmup_passes():
    report = build_testnet_warmup_report(
        inputs=good_inputs(),
        config=TestnetWarmupConfig(),
    )

    assert report.passed is True
    assert report.blocking_fail_count == 0


def test_insufficient_days_fails():
    inputs = good_inputs()
    inputs.days_completed = 3

    report = build_testnet_warmup_report(
        inputs=inputs,
        config=TestnetWarmupConfig(),
    )

    assert report.passed is False
    assert any(check["code"] == "WARMUP_DAYS_INSUFFICIENT" for check in report.checks)


def test_critical_alerts_fail():
    inputs = good_inputs()
    inputs.critical_alerts = 1

    report = build_testnet_warmup_report(
        inputs=inputs,
        config=TestnetWarmupConfig(),
    )

    assert report.passed is False
    assert any(check["code"] == "WARMUP_CRITICAL_ALERTS_HIGH" for check in report.checks)


def test_export_testnet_warmup_report(tmp_path):
    report = build_testnet_warmup_report(
        inputs=good_inputs(),
        config=TestnetWarmupConfig(),
    )

    path = export_testnet_warmup_report(
        report,
        output_dir=tmp_path,
        name="unit_warmup",
    )

    assert path.exists()