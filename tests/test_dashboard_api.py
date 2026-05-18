from dashboard.api import route_dashboard_request
from dashboard.config import DashboardConfig


def test_health_endpoint():
    status, body, content_type = route_dashboard_request(
        "/health",
        config=DashboardConfig(),
    )

    assert status == 200
    assert content_type == "application/json"
    assert b"ok" in body


def test_index_endpoint():
    status, body, content_type = route_dashboard_request(
        "/",
        config=DashboardConfig(),
    )

    assert status == 200
    assert "text/html" in content_type
    assert b"BTC Binance Futures Dashboard" in body


def test_config_endpoint():
    status, body, content_type = route_dashboard_request(
        "/dashboard/config",
        config=DashboardConfig(port=9999),
    )

    assert status == 200
    assert b"9999" in body


def test_summary_endpoint(tmp_path):
    config = DashboardConfig(
        paper_trading_dir=tmp_path,
        full_backtest_dir=tmp_path,
        model_evaluation_dir=tmp_path,
    )

    status, body, content_type = route_dashboard_request(
        "/dashboard/summary",
        config=config,
    )

    assert status == 200
    assert b"paper_trading" in body


def test_not_found_endpoint():
    status, body, content_type = route_dashboard_request(
        "/not-found",
        config=DashboardConfig(),
    )

    assert status == 404
    assert b"not_found" in body