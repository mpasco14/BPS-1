from observability.grafana_dashboard import build_grafana_dashboard_config, export_grafana_dashboard_config
from observability.metrics_registry import build_metrics_snapshot, metric_sample


def test_build_grafana_dashboard_config():
    snapshot = build_metrics_snapshot(
        metrics=[
            metric_sample(name="live_pnl", value=1),
            metric_sample(name="fill_rate", value=0.8),
        ]
    )

    dashboard = build_grafana_dashboard_config(snapshot=snapshot, title="Unit Dashboard")

    assert dashboard["title"] == "Unit Dashboard"
    assert len(dashboard["panels"]) == 2


def test_export_grafana_dashboard_config(tmp_path):
    dashboard = build_grafana_dashboard_config(title="Unit Dashboard")

    path = export_grafana_dashboard_config(dashboard, path=tmp_path / "dashboard.json")

    assert path.exists()