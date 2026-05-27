from observability.alert_rules import AlertRule, evaluate_alert_rules
from observability.metrics_registry import build_metrics_snapshot, metric_sample


def test_alert_rule_fires():
    snapshot = build_metrics_snapshot(
        metrics=[
            metric_sample(name="live_rejection_rate", value=0.2)
        ]
    )

    report = evaluate_alert_rules(
        snapshot=snapshot,
        rules=[
            AlertRule(
                rule_id="rejection_high",
                metric_name="live_rejection_rate",
                operator="gt",
                threshold=0.1,
                severity="CRITICAL",
            )
        ],
    )

    assert report.passed is False
    assert report.critical_count == 1


def test_alert_rule_passes():
    snapshot = build_metrics_snapshot(
        metrics=[
            metric_sample(name="live_rejection_rate", value=0.02)
        ]
    )

    report = evaluate_alert_rules(
        snapshot=snapshot,
        rules=[
            AlertRule(
                rule_id="rejection_high",
                metric_name="live_rejection_rate",
                operator="gt",
                threshold=0.1,
                severity="CRITICAL",
            )
        ],
    )

    assert report.passed is True
    assert report.fired_count == 0