"""
Dashboard schemas.

Responsabilidades:
- Padronizar payloads exibidos no dashboard.
- Separar dados do layout visual.
- Facilitar evolução para API externa ou frontend.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    service: str = "btc-binance-dashboard"
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MetricCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    label: str
    value: float | int | str | None
    unit: str | None = None
    status: str = "neutral"
    description: str | None = None


class PaperTradingDashboard(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    source_file: str | None = None

    metrics: dict[str, Any] = Field(default_factory=dict)
    cards: list[dict[str, Any]] = Field(default_factory=list)


class FullBacktestDashboard(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    source_file: str | None = None

    metrics: dict[str, Any] = Field(default_factory=dict)
    cards: list[dict[str, Any]] = Field(default_factory=list)


class CalibrationDashboard(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    source_file: str | None = None

    metrics: dict[str, Any] = Field(default_factory=dict)
    buckets: list[dict[str, Any]] = Field(default_factory=list)
    cards: list[dict[str, Any]] = Field(default_factory=list)


class RecentTrade(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: Any | None = None
    symbol: str | None = None
    timeframe: str | None = None
    routed: bool | None = None
    blocked: bool | None = None
    side: str | None = None
    net_pnl_usd: float | None = None
    outcome: str | None = None
    blockers: list[str] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: str = "ok"
    theme: str = "professional"
    refresh_seconds: int = 30

    paper_trading: dict[str, Any] = Field(default_factory=dict)
    full_backtest: dict[str, Any] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)

    recent_trades: list[dict[str, Any]] = Field(default_factory=list)


class DashboardPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    health: dict[str, Any]
    summary: dict[str, Any]