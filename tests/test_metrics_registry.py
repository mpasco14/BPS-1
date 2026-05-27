from observability.metrics_registry import (
    build_core_metrics_snapshot,
    build_metrics_snapshot,
    metric_sample,
    metric_value,
    normalize_metric_name,
)


def test_normalize_metric_name():
    assert normalize_metric_name("Live PnL %") == "live_pnl_"


def test_build_metrics_snapshot():
    snapshot = build_metrics_snapshot(
        metrics=[
            metric_sample(name="live_pnl", value=1.5),
            metric_sample(name="kill_switch_active", value=False),
        ]
    )

    assert snapshot.metrics_count == 2
    assert metric_value(snapshot, "live_pnl") == 1.5
    assert metric_value(snapshot, "kill_switch_active") == 0.0


def test_build_core_metrics_snapshot():
    snapshot = build_core_metrics_snapshot(
        live_performance={"fill_rate": 0.8, "net_pnl_usd": 2.0},
        live_risk_audit={"critical_findings_count": 0},
    )

    assert snapshot.metrics_count >= 3