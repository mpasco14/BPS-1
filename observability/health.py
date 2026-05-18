"""
Health checks for BTC Binance Futures bot.

Responsabilidades:
- Verificar estado básico de diretórios e configuração.
- Expor payload JSON para /health.
- Servir como base para alertas futuros.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from dashboard.config import DashboardConfig, load_dashboard_config


load_dotenv()


class ComponentHealth(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    status: str
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemHealth(BaseModel):
    model_config = ConfigDict(extra="allow")

    service: str
    status: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    checks: list[dict[str, Any]] = Field(default_factory=list)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def service_name() -> str:
    return os.getenv("OBSERVABILITY_SERVICE_NAME", "btc-binance-bot")


def directory_health(
    *,
    name: str,
    path: str | Path,
    required: bool = False,
) -> ComponentHealth:
    resolved = Path(path)

    if resolved.exists() and resolved.is_dir():
        return ComponentHealth(
            name=name,
            status="ok",
            message="directory_available",
            metadata={"path": str(resolved)},
        )

    if required:
        return ComponentHealth(
            name=name,
            status="error",
            message="required_directory_missing",
            metadata={"path": str(resolved)},
        )

    return ComponentHealth(
        name=name,
        status="warning",
        message="optional_directory_missing",
        metadata={"path": str(resolved)},
    )


def build_system_health(config: DashboardConfig | None = None) -> SystemHealth:
    resolved_config = config or load_dashboard_config()

    checks = [
        ComponentHealth(
            name="dashboard_config",
            status="ok" if resolved_config.enabled else "warning",
            message="dashboard_enabled" if resolved_config.enabled else "dashboard_disabled",
            metadata={
                "host": resolved_config.host,
                "port": resolved_config.port,
                "theme": resolved_config.theme,
            },
        ),
        directory_health(
            name="paper_trading_artifacts",
            path=resolved_config.paper_trading_dir,
            required=False,
        ),
        directory_health(
            name="full_backtest_artifacts",
            path=resolved_config.full_backtest_dir,
            required=False,
        ),
        directory_health(
            name="model_evaluation_artifacts",
            path=resolved_config.model_evaluation_dir,
            required=False,
        ),
    ]

    has_error = any(check.status == "error" for check in checks)

    status = "error" if has_error else "ok"

    return SystemHealth(
        service=service_name(),
        status=status,
        checks=[check.model_dump(mode="json") for check in checks],
    )


def health_to_dict(health: SystemHealth) -> dict[str, Any]:
    return health.model_dump(mode="json")