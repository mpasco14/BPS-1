from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


RuntimeEnvironment = Literal["development", "paper", "testnet", "micro_live", "live", "production"]
ExecutionMode = Literal["paper", "testnet", "live"]
MachineRole = Literal["primary", "standby", "observer"]


class RuntimeContextConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/system_integration")

    environment: RuntimeEnvironment = "development"
    session_name: str = "local_session"
    operator: str = "operator"
    machine_role: MachineRole = "primary"
    release_version: str = "0.22.0"


class IntegratedRuntimeContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "integrated_runtime_context"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    context_id: str = Field(default_factory=lambda: f"runtime_{uuid4().hex}")

    environment: RuntimeEnvironment = "development"
    execution_mode: ExecutionMode = "paper"
    session_name: str = "local_session"
    operator: str = "operator"
    machine_role: MachineRole = "primary"

    release_version: str = "0.22.0"
    git_commit: str | None = None

    config_profile: str = "conservative"
    storage_backend: str = "jsonl"

    allow_live_trading: bool = False
    risk_allow_live_trading: bool = False
    live_order_adapter_enabled: bool = False
    live_order_adapter_dry_run: bool = True
    live_order_adapter_allow_submission: bool = False

    safe_mode_active: bool = False
    kill_switch_active: bool = False

    feature_flags: dict[str, bool] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def normalize_environment(value: str) -> RuntimeEnvironment:
    normalized = value.strip().lower()

    if normalized in {"development", "paper", "testnet", "micro_live", "live", "production"}:
        return normalized  # type: ignore[return-value]

    return "development"


def normalize_execution_mode(value: str) -> ExecutionMode:
    normalized = value.strip().lower()

    if normalized in {"paper", "testnet", "live"}:
        return normalized  # type: ignore[return-value]

    return "paper"


def normalize_machine_role(value: str) -> MachineRole:
    normalized = value.strip().lower()

    if normalized in {"primary", "standby", "observer"}:
        return normalized  # type: ignore[return-value]

    return "primary"


def get_git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError:
        return None

    if completed.returncode != 0:
        return None

    return completed.stdout.strip() or None


def load_runtime_context_config() -> RuntimeContextConfig:
    return RuntimeContextConfig(
        output_dir=Path(os.getenv("RUNTIME_CONTEXT_OUTPUT_DIR", "artifacts/system_integration")),
        environment=normalize_environment(os.getenv("RUNTIME_CONTEXT_ENVIRONMENT", "development")),
        session_name=os.getenv("RUNTIME_CONTEXT_SESSION_NAME", "local_session"),
        operator=os.getenv("RUNTIME_CONTEXT_OPERATOR", "operator"),
        machine_role=normalize_machine_role(os.getenv("RUNTIME_CONTEXT_MACHINE_ROLE", "primary")),
        release_version=os.getenv("RUNTIME_CONTEXT_RELEASE_VERSION", "0.22.0"),
    )


def build_integrated_runtime_context(
    *,
    environment: RuntimeEnvironment | None = None,
    execution_mode: ExecutionMode | None = None,
    session_name: str | None = None,
    operator: str | None = None,
    machine_role: MachineRole | None = None,
    feature_flags: dict[str, bool] | None = None,
    metadata: dict[str, Any] | None = None,
) -> IntegratedRuntimeContext:
    config = load_runtime_context_config()

    resolved_execution_mode = execution_mode or normalize_execution_mode(os.getenv("BINANCE_EXECUTION_MODE", "paper"))

    return IntegratedRuntimeContext(
        environment=environment or config.environment,
        execution_mode=resolved_execution_mode,
        session_name=session_name or config.session_name,
        operator=operator or config.operator,
        machine_role=machine_role or config.machine_role,
        release_version=config.release_version,
        git_commit=get_git_commit(),
        config_profile=os.getenv("CONFIG_DEFAULT_PROFILE", "conservative"),
        storage_backend=os.getenv("STORAGE_DEFAULT_BACKEND", "jsonl"),
        allow_live_trading=env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
        risk_allow_live_trading=env_bool("RISK_ALLOW_LIVE_TRADING", False),
        live_order_adapter_enabled=env_bool("LIVE_ORDER_ADAPTER_ENABLED", False),
        live_order_adapter_dry_run=env_bool("LIVE_ORDER_ADAPTER_DRY_RUN", True),
        live_order_adapter_allow_submission=env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
        safe_mode_active=env_bool("SAFE_MODE_ACTIVE", False),
        kill_switch_active=env_bool("KILL_SWITCH_ACTIVE", False),
        feature_flags=feature_flags or {},
        metadata=metadata or {},
    )


def runtime_context_is_live_intent(context: IntegratedRuntimeContext | dict[str, Any]) -> bool:
    parsed = context if isinstance(context, IntegratedRuntimeContext) else IntegratedRuntimeContext.model_validate(context)

    return (
        parsed.execution_mode == "live"
        or parsed.environment in {"live", "production", "micro_live"}
        or parsed.live_order_adapter_enabled
        or parsed.live_order_adapter_allow_submission
    )


def export_runtime_context(
    context: IntegratedRuntimeContext,
    *,
    output_dir: str | Path | None = None,
    name: str = "runtime_context_latest",
) -> Path:
    config = load_runtime_context_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(context.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path