from ops.live_risk_audit import (
    LiveRiskAuditConfig,
    build_live_risk_audit_report,
    export_live_risk_audit_report,
)
from ops.live_session_recorder import LiveRecordedEvent, build_demo_live_session_events


def test_live_risk_audit_passes_demo_events():
    events = build_demo_live_session_events("unit_risk")

    report = build_live_risk_audit_report(
        events=events,
        session_name="unit_risk",
        config=LiveRiskAuditConfig(),
    )

    assert report.passed is True
    assert report.status == "PASS"


def test_live_risk_audit_blocks_margin_violation():
    events = [
        LiveRecordedEvent(
            event_id="bad_margin",
            session_name="unit_risk_bad",
            event_type="SUBMITTED",
            status="NEW",
            margin_usd=100,
            notional_usd=600,
            leverage=30,
            preflight_passed=True,
            live_guard_passed=True,
            no_trade_passed=True,
            risk_state_status="OK",
        )
    ]

    report = build_live_risk_audit_report(
        events=events,
        session_name="unit_risk_bad",
        config=LiveRiskAuditConfig(max_margin_usd=20),
    )

    assert report.passed is False
    assert any(finding["code"] == "margin_above_limit" for finding in report.findings)


def test_live_risk_audit_export(tmp_path):
    events = build_demo_live_session_events("unit_risk_export")

    report = build_live_risk_audit_report(
        events=events,
        session_name="unit_risk_export",
    )

    path = export_live_risk_audit_report(
        report,
        output_dir=tmp_path,
        name="unit_risk",
    )

    assert path.exists()