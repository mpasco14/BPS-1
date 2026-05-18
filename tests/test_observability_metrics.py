from dashboard.config import DashboardConfig
from observability.metrics import (
    MetricSample,
    build_metrics_text,
    build_observability_samples,
    metric_name,
    render_prometheus_text,
    route_observability_request,
)


def test_metric_name_normalization():
    assert metric_name("BTC Bot PnL USD") == "btc_bot_pnl_usd"
    assert metric_name("123 abc") == "metric_123_abc"


def test_render_prometheus_text():
    text = render_prometheus_text(
        [
            MetricSample(
                name="btc_bot_test_metric",
                value=1.0,
                help_text="Test metric",
                labels={"component": "unit"},
            )
        ]
    )

    assert "# HELP btc_bot_test_metric Test metric" in text
    assert 'btc_bot_test_metric{component="unit"} 1.0' in text


def test_build_observability_samples(tmp_path):
    config = DashboardConfig(
        paper_trading_dir=tmp_path,
        full_backtest_dir=tmp_path,
        model_evaluation_dir=tmp_path,
    )

    samples = build_observability_samples(config)

    assert any(sample.name == "btc_bot_up" for sample in samples)


def test_build_metrics_text(tmp_path):
    config = DashboardConfig(
        paper_trading_dir=tmp_path,
        full_backtest_dir=tmp_path,
        model_evaluation_dir=tmp_path,
    )

    text = build_metrics_text(config)

    assert "btc_bot_up" in text


def test_route_metrics_endpoint(tmp_path):
    config = DashboardConfig(
        paper_trading_dir=tmp_path,
        full_backtest_dir=tmp_path,
        model_evaluation_dir=tmp_path,
    )

    status, body, content_type = route_observability_request(
        "/metrics",
        config=config,
    )

    assert status == 200
    assert b"btc_bot_up" in body
    assert "text/plain" in content_type


def test_route_health_endpoint(tmp_path):
    config = DashboardConfig(
        paper_trading_dir=tmp_path,
        full_backtest_dir=tmp_path,
        model_evaluation_dir=tmp_path,
    )

    status, body, content_type = route_observability_request(
        "/health",
        config=config,
    )

    assert status == 200
    assert b"status" in body
    assert content_type == "application/json"


def test_route_not_found(tmp_path):
    config = DashboardConfig(
        paper_trading_dir=tmp_path,
        full_backtest_dir=tmp_path,
        model_evaluation_dir=tmp_path,
    )

    status, body, content_type = route_observability_request(
        "/missing",
        config=config,
    )

    assert status == 404
    assert b"not_found" in body