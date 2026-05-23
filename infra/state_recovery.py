from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


RecoveryStatus = Literal["READY", "RECOVERY_REQUIRED", "BLOCKED", "INIT_REQUIRED"]


class StateRecoveryConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/infra")
    state_file: Path = Path("artifacts/infra/runtime_state_snapshot.json")

    max_state_age_seconds: float = 300.0
    block_if_risk_not_ok: bool = True


class RuntimeStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "runtime_state_snapshot"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str = "runtime"
    last_event_id: str | None = None

    open_orders: list[dict[str, Any]] = Field(default_factory=list)
    open_positions: list[dict[str, Any]] = Field(default_factory=list)

    risk_state_status: str = "OK"
    kill_switch_active: bool = False
    safe_mode_active: bool = False

    last_known_price: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateRecoveryReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "state_recovery"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: RecoveryStatus
    passed: bool

    state_age_seconds: float | None = None
    open_orders_count: int = 0
    open_positions_count: int = 0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recovery_actions: list[str] = Field(default_factory=list)

    snapshot: dict[str, Any] | None = None
    config: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_state_recovery_config() -> StateRecoveryConfig:
    return StateRecoveryConfig(
        output_dir=Path(os.getenv("STATE_RECOVERY_OUTPUT_DIR", "artifacts/infra")),
        state_file=Path(os.getenv("STATE_RECOVERY_FILE", "artifacts/infra/runtime_state_snapshot.json")),
        max_state_age_seconds=env_float("STATE_RECOVERY_MAX_STATE_AGE_SECONDS", 300),
        block_if_risk_not_ok=env_bool("STATE_RECOVERY_BLOCK_IF_RISK_NOT_OK", True),
    )


def export_runtime_state_snapshot(
    snapshot: RuntimeStateSnapshot,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_state_recovery_config()
    output_path = Path(path or config.state_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def load_runtime_state_snapshot(
    path: str | Path | None = None,
) -> RuntimeStateSnapshot | None:
    config = load_state_recovery_config()
    input_path = Path(path or config.state_file)

    if not input_path.exists():
        return None

    return RuntimeStateSnapshot.model_validate(json.loads(input_path.read_text(encoding="utf-8")))


def seconds_old(timestamp: datetime, *, now: datetime | None = None) -> float:
    resolved_now = now or datetime.now(timezone.utc)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)

    return max(0.0, (resolved_now - timestamp).total_seconds())


def build_state_recovery_report(
    *,
    snapshot: RuntimeStateSnapshot | dict[str, Any] | None = None,
    state_file: str | Path | None = None,
    config: StateRecoveryConfig | None = None,
    now: datetime | None = None,
) -> StateRecoveryReport:
    resolved_config = config or load_state_recovery_config()

    if snapshot is None:
        loaded = load_runtime_state_snapshot(state_file)
        if loaded is None:
            return StateRecoveryReport(
                status="INIT_REQUIRED",
                passed=False,
                blockers=["state_snapshot_missing"],
                recovery_actions=["initialize_state_snapshot", "block_new_orders_until_initialized"],
                config=resolved_config.model_dump(mode="json"),
            )
        resolved_snapshot = loaded
    else:
        resolved_snapshot = snapshot if isinstance(snapshot, RuntimeStateSnapshot) else RuntimeStateSnapshot.model_validate(snapshot)

    age = seconds_old(resolved_snapshot.updated_at, now=now)

    blockers: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []

    if age > resolved_config.max_state_age_seconds:
        warnings.append("state_snapshot_stale")
        actions.append("refresh_state_from_exchange")

    if resolved_snapshot.open_orders:
        warnings.append("open_orders_present")
        actions.append("reconcile_open_orders")

    if resolved_snapshot.open_positions:
        warnings.append("open_positions_present")
        actions.append("reconcile_open_positions")

    if resolved_snapshot.kill_switch_active:
        blockers.append("kill_switch_active")
        actions.append("keep_new_orders_blocked")

    if resolved_snapshot.safe_mode_active:
        warnings.append("safe_mode_active")
        actions.append("operator_review_required")

    if resolved_config.block_if_risk_not_ok and resolved_snapshot.risk_state_status != "OK":
        blockers.append("risk_state_not_ok")
        actions.append("block_new_orders_until_risk_state_ok")

    if blockers:
        status: RecoveryStatus = "BLOCKED"
        passed = False
    elif warnings:
        status = "RECOVERY_REQUIRED"
        passed = True
    else:
        status = "READY"
        passed = True

    return StateRecoveryReport(
        status=status,
        passed=passed,
        state_age_seconds=round(age, 4),
        open_orders_count=len(resolved_snapshot.open_orders),
        open_positions_count=len(resolved_snapshot.open_positions),
        blockers=blockers,
        warnings=warnings,
        recovery_actions=actions,
        snapshot=resolved_snapshot.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_state_recovery_report(
    report: StateRecoveryReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "state_recovery_latest",
) -> Path:
    config = load_state_recovery_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path