from ops.capital_ramp import (
    CapitalRampConfig,
    CapitalRampInputs,
    build_capital_ramp_report,
    export_capital_ramp_report,
)


def good_inputs():
    return CapitalRampInputs(
        trades_count=30,
        win_rate=0.55,
        profit_factor=1.3,
        max_drawdown_pct=0.05,
        expected_calibration_error=0.05,
        critical_alerts=0,
    )


def test_capital_ramp_recommends_advance_with_good_inputs():
    report = build_capital_ramp_report(
        inputs=good_inputs(),
        config=CapitalRampConfig(current_level=1, allow_auto_advance=False),
    )

    assert report.passed is True
    assert report.advance_recommended is True
    assert report.auto_advance_allowed is False


def test_capital_ramp_blocks_on_drawdown():
    inputs = good_inputs()
    inputs.max_drawdown_pct = 0.30

    report = build_capital_ramp_report(
        inputs=inputs,
        config=CapitalRampConfig(current_level=1),
    )

    assert report.passed is False
    assert any(check["code"] == "DRAWDOWN_HIGH" for check in report.checks)


def test_export_capital_ramp_report(tmp_path):
    report = build_capital_ramp_report(
        inputs=good_inputs(),
        config=CapitalRampConfig(current_level=1),
    )

    path = export_capital_ramp_report(
        report,
        output_dir=tmp_path,
        name="unit_capital_ramp",
    )

    assert path.exists()