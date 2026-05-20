from ops.strategy_health import (
    StrategyHealthInput,
    build_strategy_health_report,
    export_strategy_health_report,
)


def test_strategy_health_healthy():
    report = build_strategy_health_report(
        input_data=StrategyHealthInput(
            trades_count=50,
            net_pnl_usd=10,
            max_drawdown_pct=0.03,
            profit_factor=1.3,
            win_rate=0.6,
            fill_rate=0.8,
            rejection_rate=0.01,
            expected_calibration_error=0.05,
            ood_rate=0.05,
            discipline_score=0.95,
            risk_state_status="OK",
        )
    )

    assert report.status == "HEALTHY"
    assert report.passed is True


def test_strategy_health_blocks_risk_state():
    report = build_strategy_health_report(
        input_data=StrategyHealthInput(
            risk_state_status="BLOCKED",
            max_drawdown_pct=0.01,
            profit_factor=1.5,
            win_rate=0.7,
            fill_rate=0.8,
            rejection_rate=0.0,
            expected_calibration_error=0.01,
            ood_rate=0.01,
            discipline_score=1.0,
        )
    )

    assert report.status == "BLOCKED"
    assert "risk_state_not_ok" in report.blockers


def test_export_strategy_health_report(tmp_path):
    report = build_strategy_health_report(input_data=StrategyHealthInput())

    path = export_strategy_health_report(
        report,
        output_dir=tmp_path,
        name="unit_strategy_health",
    )

    assert path.exists()