from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


LiveSessionStatus = Literal["RUNNING", "WARN", "PAUSED", "STOPPED", "BLOCKED"]


class LiveSessionSupervisorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live_ops")

    max_heartbeat_age_seconds: float = 60.0
    max_drawdown_usd: float = 20.0
    max_rejection_rate: float = 0.15
    max_ood_rate: float = 0.20
    max_consecutive_errors: int = 3


class LiveSessionTelemetry(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_name: str = "live_session"
    environment: str = "paper"

    heartbeat_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    safe_mode_active: bool = False
    kill_switch_active: bool = False

    open_positions_count: int = 0
    open_orders_count: int = 0

    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    drawdown_usd: float = 0.0

    fill_rate: float = 1.0
    rejection_rate: float = 0.0
    ood_rate: float = 0.0

    consecutive_errors: int = 0

    model_valid: bool = True
    exchange_connected: bool = True
    websocket_connected: bool = True

    metadata: dict[str, Any] = Field(default_factory=dict)


class LiveSessionSupervisorReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_session_supervisor"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str
    status: LiveSessionStatus
    allowed_to_continue: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)

    telemetry: dict[str, Any]
    config: dict[str, Any]


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_live_session_supervisor_config() -> LiveSessionSupervisorConfig:
    return LiveSessionSupervisorConfig(
        output_dir=Path(os.getenv("LIVE_SESSION_SUPERVISOR_OUTPUT_DIR", "artifacts/live_ops")),
        max_heartbeat_age_seconds=env_float("LIVE_SESSION_MAX_HEARTBEAT_AGE_SECONDS", 60),
        max_drawdown_usd=env_float("LIVE_SESSION_MAX_DRAWDOWN_USD", 20),
        max_rejection_rate=env_float("LIVE_SESSION_MAX_REJECTION_RATE", 0.15),
        max_ood_rate=env_float("LIVE_SESSION_MAX_OOD_RATE", 0.20),
        max_consecutive_errors=env_int("LIVE_SESSION_MAX_CONSECUTIVE_ERRORS", 3),
    )


def heartbeat_age_seconds(heartbeat_at: datetime, *, now: datetime | None = None) -> float:
    resolved_now = now or datetime.now(timezone.utc)

    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)

    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)

    return max(0.0, (resolved_now - heartbeat_at).total_seconds())


def supervise_live_session(
    *,
    telemetry: LiveSessionTelemetry | dict[str, Any],
    config: LiveSessionSupervisorConfig | None = None,
    now: datetime | None = None,
) -> LiveSessionSupervisorReport:
    resolved_config = config or load_live_session_supervisor_config()
    parsed = telemetry if isinstance(telemetry, LiveSessionTelemetry) else LiveSessionTelemetry.model_validate(telemetry)

    blockers: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []

    age = heartbeat_age_seconds(parsed.heartbeat_at, now=now)

    if age > resolved_config.max_heartbeat_age_seconds:
        blockers.append("heartbeat_stale")
        actions.append("pause_session_and_check_process_health")

    if parsed.kill_switch_active:
        blockers.append("kill_switch_active")
        actions.append("block_new_orders_and_cancel_open_orders")

    if parsed.safe_mode_active:
        warnings.append("safe_mode_active")
        actions.append("allow_reduce_only_and_operator_review")

    if parsed.drawdown_usd > resolved_config.max_drawdown_usd:
        blockers.append("drawdown_above_limit")
        actions.append("activate_kill_switch")

    if parsed.rejection_rate > resolved_config.max_rejection_rate:
        warnings.append("rejection_rate_above_limit")
        actions.append("reduce_order_flow_and_inspect_exchange_errors")

    if parsed.ood_rate > resolved_config.max_ood_rate:
        warnings.append("ood_rate_above_limit")
        actions.append("switch_model_to_watch_mode")

    if parsed.consecutive_errors >= resolved_config.max_consecutive_errors:
        blockers.append("consecutive_errors_above_limit")
        actions.append("pause_session_and_emit_incident")

    if not parsed.model_valid:
        blockers.append("model_invalid")
        actions.append("block_signal_generation")

    if not parsed.exchange_connected:
        blockers.append("exchange_disconnected")
        actions.append("pause_session_until_exchange_recovers")

    if not parsed.websocket_connected:
        warnings.append("websocket_disconnected")
        actions.append("reconnect_websocket_and_reduce_order_flow")

    allowed = not blockers

    if blockers:
        status: LiveSessionStatus = "BLOCKED"
    elif parsed.safe_mode_active:
        status = "PAUSED"
    elif warnings:
        status = "WARN"
    else:
        status = "RUNNING"

    return LiveSessionSupervisorReport(
        session_name=parsed.session_name,
        status=status,
        allowed_to_continue=allowed,
        blockers=blockers,
        warnings=warnings,
        recommended_actions=sorted(set(actions)),
        telemetry=parsed.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_live_session_supervisor_report(
    report: LiveSessionSupervisorReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "live_session_supervisor_latest",
) -> Path:
    config = load_live_session_supervisor_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path