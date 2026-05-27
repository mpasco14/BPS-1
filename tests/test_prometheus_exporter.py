from observability.metrics_registry import build_metrics_snapshot, metric_sample
from observability.prometheus_exporter import render_prometheus_text, export_prometheus_metrics


def test_render_prometheus_text():
    snapshot = build_metrics_snapshot(
        metrics=[
            metric_sample(
                name="live_fill_rate",
                value=0.75,
                labels={"symbol": "BTCUSDT"},
            )
        ]
    )

    text = render_prometheus_text(snapshot, namespace="btc_bot")

    assert "btc_bot_live_fill_rate" in text
    assert 'symbol="BTCUSDT"' in text
    assert "0.75" in text


def test_export_prometheus_metrics(tmp_path):
    snapshot = build_metrics_snapshot(metrics=[metric_sample(name="x", value=1)])

    path = export_prometheus_metrics(snapshot, path=tmp_path / "metrics.prom")

    assert path.exists()