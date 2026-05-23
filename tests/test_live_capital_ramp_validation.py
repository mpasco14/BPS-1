from ops.live_capital_ramp_validation import (
    LiveCapitalRampValidationConfig,
    build_live_capital_ramp_validation_report,
    export_live_capital_ramp_validation_report,
)
from ops.live_performance_analyzer import build_live_performance_report
from ops.live_risk_audit import build_live_risk_audit_report
from ops.live_session_recorder import build_demo_live_session_events


def test_live_capital_ramp_holds_when_low_sample():
    events = build_demo_live_session_events("unit_ramp")
    performance = build_live_performance_report(events=events, session_name="unit_ramp")
    risk = build_live_risk_audit_report(events=events, session_name="unit_ramp")

    report = build_live_capital_ramp_validation_report(
        performance=performance,
        risk_audit=risk,
        config=LiveCapitalRampValidationConfig(min_trades=20),
    )

    assert report.action == "HOLD_LEVEL"
    assert report.passed is True
    assert report.capital_increase_allowed is False


def test_live_capital_ramp_pauses_on_risk_failure():
    events = build_demo_live_session_events("unit_ramp_bad")
    events[2].margin_usd = 100

    performance = build_live_performance_report(events=events, session_name="unit_ramp_bad")
    risk = build_live_risk_audit_report(events=events, session_name="unit_ramp_bad")

    report = build_live_capital_ramp_validation_report(
        performance=performance,
        risk_audit=risk,
    )

    assert report.action == "PAUSE_LIVE"
    assert report.passed is False


def test_export_live_capital_ramp_validation(tmp_path):
    events = build_demo_live_session_events("unit_ramp_export")
    performance = build_live_performance_report(events=events, session_name="unit_ramp_export")
    risk = build_live_risk_audit_report(events=events, session_name="unit_ramp_export")

    report = build_live_capital_ramp_validation_report(
        performance=performance,
        risk_audit=risk,
    )

    path = export_live_capital_ramp_validation_report(
        report,
        output_dir=tmp_path,
        name="unit_ramp",
    )

    assert path.exists()