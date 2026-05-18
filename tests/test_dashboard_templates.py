from dashboard.config import DashboardConfig
from dashboard.templates import render_dashboard_html


def test_render_dashboard_html_contains_title():
    html = render_dashboard_html(DashboardConfig())

    assert "BTC Binance Futures Dashboard" in html
    assert "/dashboard/summary" in html


def test_render_dashboard_html_uses_theme_name():
    html = render_dashboard_html(DashboardConfig(theme="dark"))

    assert "tema: dark" in html