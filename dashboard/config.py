"""
Dashboard configuration.

Responsabilidades:
- Centralizar parâmetros do dashboard.
- Evitar hardcode de paths, tema e refresh.
- Facilitar evolução para frontend/API/Grafana.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict


load_dotenv()


class DashboardConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True

    host: str = "127.0.0.1"
    port: int = 8050
    refresh_seconds: int = 30

    theme: str = "professional"

    paper_trading_dir: Path = Path("artifacts/paper_trading")
    full_backtest_dir: Path = Path("artifacts/full_backtest")
    model_evaluation_dir: Path = Path("artifacts/model_evaluation")

    show_paper_trading: bool = True
    show_full_backtest: bool = True
    show_calibration: bool = True
    show_risk: bool = True

    max_recent_trades: int = 50


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def env_path(name: str, default: str) -> Path:
    return Path(os.getenv(name, default))


def load_dashboard_config() -> DashboardConfig:
    return DashboardConfig(
        enabled=env_bool("DASHBOARD_ENABLED", True),
        host=os.getenv("DASHBOARD_HOST", "127.0.0.1"),
        port=env_int("DASHBOARD_PORT", 8050),
        refresh_seconds=env_int("DASHBOARD_REFRESH_SECONDS", 30),
        theme=os.getenv("DASHBOARD_THEME", "professional"),
        paper_trading_dir=env_path("DASHBOARD_PAPER_TRADING_DIR", "artifacts/paper_trading"),
        full_backtest_dir=env_path("DASHBOARD_FULL_BACKTEST_DIR", "artifacts/full_backtest"),
        model_evaluation_dir=env_path("DASHBOARD_MODEL_EVALUATION_DIR", "artifacts/model_evaluation"),
        show_paper_trading=env_bool("DASHBOARD_SHOW_PAPER_TRADING", True),
        show_full_backtest=env_bool("DASHBOARD_SHOW_FULL_BACKTEST", True),
        show_calibration=env_bool("DASHBOARD_SHOW_CALIBRATION", True),
        show_risk=env_bool("DASHBOARD_SHOW_RISK", True),
        max_recent_trades=env_int("DASHBOARD_MAX_RECENT_TRADES", 50),
    )


def dashboard_config_to_dict(config: DashboardConfig) -> dict:
    payload = config.model_dump(mode="json")
    return payload