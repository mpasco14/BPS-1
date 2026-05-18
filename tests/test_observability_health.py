from dashboard.config import DashboardConfig
from observability.health import build_system_health, directory_health, health_to_dict


def test_directory_health_warning_when_optional_missing(tmp_path):
    missing = tmp_path / "missing"

    health = directory_health(
        name="optional_dir",
        path=missing,
        required=False,
    )

    assert health.status == "warning"


def test_directory_health_error_when_required_missing(tmp_path):
    missing = tmp_path / "missing"

    health = directory_health(
        name="required_dir",
        path=missing,
        required=True,
    )

    assert health.status == "error"


def test_build_system_health(tmp_path):
    config = DashboardConfig(
        paper_trading_dir=tmp_path,
        full_backtest_dir=tmp_path,
        model_evaluation_dir=tmp_path,
    )

    health = build_system_health(config)

    assert health.service
    assert health.status == "ok"
    assert len(health.checks) >= 1


def test_health_to_dict(tmp_path):
    config = DashboardConfig(
        paper_trading_dir=tmp_path,
        full_backtest_dir=tmp_path,
        model_evaluation_dir=tmp_path,
    )

    payload = health_to_dict(build_system_health(config))

    assert payload["status"] == "ok"