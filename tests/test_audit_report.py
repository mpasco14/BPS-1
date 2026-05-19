from ops.audit_report import (
    WeeklyAuditConfig,
    audit_alerts,
    audit_backtest,
    audit_calibration,
    audit_paper_trading,
    build_weekly_audit_report,
    export_weekly_audit_report,
)


def test_audit_paper_trading_ok():
    items = audit_paper_trading(
        report={
            "metrics": {
                "fill_rate": 0.8,
                "net_pnl_usd": 10,
                "win_rate": 0.6,
            }
        },
        config=WeeklyAuditConfig(),
    )

    codes = {item.code for item in items}

    assert "PAPER_FILL_RATE_OK" in codes
    assert "PAPER_PNL_POSITIVE" in codes


def test_audit_backtest_warns_on_bad_metrics():
    items = audit_backtest(
        report={
            "metrics": {
                "profit_factor": 0.8,
                "max_drawdown_pct": 0.3,
                "net_pnl_usd": -10,
            }
        },
        config=WeeklyAuditConfig(),
    )

    assert any(item.status == "WARN" for item in items)


def test_audit_calibration_warns_on_high_ece():
    items = audit_calibration(
        report={
            "brier_score": 0.1,
            "expected_calibration_error": 0.3,
        },
        config=WeeklyAuditConfig(),
    )

    assert any(item.code == "CALIBRATION_ECE_HIGH" for item in items)


def test_audit_alerts_critical_fail():
    items = audit_alerts(
        report={
            "critical_count": 1,
            "warning_count": 0,
        }
    )

    assert items[0].status == "FAIL"


def test_build_weekly_audit_report_disabled():
    report = build_weekly_audit_report(
        config=WeeklyAuditConfig(enabled=False)
    )

    assert report.status == "FAIL"


def test_export_weekly_audit_report(tmp_path):
    report = build_weekly_audit_report(
        config=WeeklyAuditConfig(enabled=False)
    )

    path = export_weekly_audit_report(
        report,
        output_dir=tmp_path,
        name="unit_audit",
    )

    assert path.exists()