from dashboard.config import DashboardConfig
from dashboard.theme_loader import DEFAULT_THEME, load_theme, load_theme_for_config


def test_load_default_theme_when_missing():
    theme = load_theme("theme_that_does_not_exist")

    assert theme["name"] == DEFAULT_THEME["name"]
    assert "background" in theme


def test_load_professional_theme():
    theme = load_theme("professional")

    assert theme["name"] == "professional"
    assert "surface" in theme


def test_load_theme_for_config():
    config = DashboardConfig(theme="dark")
    theme = load_theme_for_config(config)

    assert theme["name"] == "dark"