from observability.alert_rules import AlertRule, evaluate_alert_rules
from observability.incident_report import generate_incident_report, export_incident_report
from observability.metrics_registry import build_metrics_snapshot, metric_sample


def test_generate_incident_report_active():
    snapshot = build_metrics_snapshot(
        metrics=[
            metric_sample(name="risk_findings", value=1)
        ]
    )

    alerts = evaluate_alert_rules(
        snapshot=snapshot,
        rules=[
            AlertRule(
                rule_id="risk_critical_findings",
                metric_name="risk_findings",
                operator="gt",
                threshold=0,
                severity="CRITICAL",
            )
        ],
    )

    report = generate_incident_report(alert_report=alerts, metrics_snapshot=snapshot)

    assert report.active is True
    assert report.severity == "CRITICAL"
    assert report.recommended_actions


def test_generate_incident_report_inactive():
    snapshot = build_metrics_snapshot(
        metrics=[
            metric_sample(name="risk_findings", value=0)
        ]
    )

    alerts = evaluate_alert_rules(
        snapshot=snapshot,
        rules=[
            AlertRule(
                rule_id="risk_critical_findings",
                metric_name="risk_findings",
                operator="gt",
                threshold=0,
                severity="CRITICAL",
            )
        ],
    )

    report = generate_incident_report(alert_report=alerts, metrics_snapshot=snapshot)

    assert report.active is False
    assert report.severity == "NONE"


def test_export_incident_report(tmp_path):
    snapshot = build_metrics_snapshot(metrics=[metric_sample(name="x", value=0)])
    alerts = evaluate_alert_rules(snapshot=snapshot, rules=[])
    report = generate_incident_report(alert_report=alerts, metrics_snapshot=snapshot)

    path = export_incident_report(report, output_dir=tmp_path, name="unit_incident")

    assert path.exists()