from ops.runbook import (
    RunbookConfig,
    RunbookInputs,
    build_runbook_report,
    evaluate_live_requirements,
    evaluate_live_trading_flags,
    export_runbook_report,
)


def good_inputs():
    return RunbookInputs(
        paper_days_completed=14,
        testnet_days_completed=14,
        paper_trades_count=50,
        testnet_trades_count=50,
        paper_fill_rate=0.75,
        testnet_fill_rate=0.75,
        backtest_profit_factor=1.5,
        backtest_sharpe=1.0,
        backtest_max_drawdown_pct=0.10,
        backtest_net_pnl_usd=100,
        calibration_ece=0.05,
        calibration_brier_score=0.10,
        security_check_passed=True,
        compliance_check_passed=True,
        legal_review_approved=True,
        testnet_completed=True,
        binance_allow_live_trading=False,
        risk_allow_live_trading=False,
        binance_execution_mode="paper",
    )


def test_build_runbook_report_testnet_passes_without_blocking_failures():
    report = build_runbook_report(
        stage="testnet",
        inputs=good_inputs(),
        config=RunbookConfig(
            require_compliance_check_pass=False,
        ),
    )

    assert report.passed is True
    assert report.blocking_fail_count == 0


def test_live_requires_testnet_and_legal_review():
    inputs = good_inputs()
    inputs.testnet_completed = False
    inputs.legal_review_approved = False

    steps = evaluate_live_requirements(
        inputs=inputs,
        config=RunbookConfig(),
        stage="live",
    )

    codes = {step.code for step in steps}

    assert "TESTNET_NOT_COMPLETED_FOR_LIVE" in codes
    assert "LEGAL_REVIEW_REQUIRED_FOR_LIVE" in codes


def test_live_trading_flags_fail_when_live_enabled():
    inputs = good_inputs()
    inputs.binance_allow_live_trading = True

    steps = evaluate_live_trading_flags(
        inputs=inputs,
        config=RunbookConfig(),
    )

    assert steps[0].status == "FAIL"
    assert steps[0].blocking is True


def test_build_runbook_report_disabled():
    report = build_runbook_report(
        stage="testnet",
        inputs=good_inputs(),
        config=RunbookConfig(enabled=False),
    )

    assert report.passed is False
    assert report.status == "FAIL"


def test_export_runbook_report(tmp_path):
    report = build_runbook_report(
        stage="testnet",
        inputs=good_inputs(),
        config=RunbookConfig(require_compliance_check_pass=False),
    )

    path = export_runbook_report(
        report,
        output_dir=tmp_path,
        name="unit_runbook",
    )

    assert path.exists()