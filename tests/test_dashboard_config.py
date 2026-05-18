from dashboard.config import DashboardConfig, dashboard_config_to_dict, load_dashboard_config


def test_dashboard_config_defaults():
    config = DashboardConfig()

    assert config.enabled is True
    assert config.host == "127.0.0.1"
    assert config.port == 8050


def test_dashboard_config_to_dict():
    config = DashboardConfig(theme="professional")
    payload = dashboard_config_to_dict(config)

    assert payload["theme"] == "professional"


def test_load_dashboard_config(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PORT", "9000")
    monkeypatch.setenv("DASHBOARD_THEME", "dark")

    config = load_dashboard_config()

    assert config.port == 9000
    assert config.theme == "dark"