from ops.compliance_check import (
    ComplianceConfig,
    check_live_trading_disabled,
    check_operator_country,
    export_compliance_report,
    run_compliance_checks,
)


def test_check_live_trading_disabled_pass(monkeypatch):
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("BINANCE_EXECUTION_MODE", "paper")

    result = check_live_trading_disabled(ComplianceConfig())

    assert result.status == "PASS"


def test_check_live_trading_disabled_fail(monkeypatch):
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "true")

    result = check_live_trading_disabled(ComplianceConfig())

    assert result.status == "FAIL"
    assert result.blocking is True


def test_check_operator_country_br_warn():
    result = check_operator_country(
        ComplianceConfig(operator_country="BR")
    )

    assert result.status == "WARN"


def test_run_compliance_checks():
    report = run_compliance_checks(
        ComplianceConfig(
            require_paper_trading=False,
            require_backtest_positive=False,
            require_calibration_valid=False,
            legal_review_approved=False,
        )
    )

    assert report.checks_count >= 1
    assert report.status in {"PASS", "FAIL"}


def test_export_compliance_report(tmp_path):
    report = run_compliance_checks(
        ComplianceConfig(
            require_paper_trading=False,
            require_backtest_positive=False,
            require_calibration_valid=False,
        )
    )

    path = export_compliance_report(
        report,
        output_dir=tmp_path,
    )

    assert path.exists()