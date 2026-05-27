from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


OverrideStatus = Literal["APPROVED", "BLOCKED", "WARN"]


class RuntimeOverrideConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/config")

    require_human_approval_for_live: bool = True
    block_protected_keys: bool = True
    max_ttl_minutes: int = 60

    protected_key_patterns: list[str] = Field(
        default_factory=lambda: [
            "allow_live",
            "live_order_adapter_allow_submission",
            "binance_allow_live_trading",
            "risk_allow_live_trading",
            "max_leverage",
            "max_margin",
            "max_notional",
            "kill_switch",
            "production_guard",
        ]
    )


class RuntimeOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    override_id: str
    key: str
    old_value: Any | None = None
    new_value: Any

    environment: str = "development"
    requested_by: str = "operator"
    approved_by: str | None = None

    reason: str
    ttl_minutes: int = 15

    human_approval_valid: bool = False
    emergency_change: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeOverrideDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "runtime_override_guard"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    override_id: str
    key: str
    status: OverrideStatus
    approved: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    request: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_runtime_override_config() -> RuntimeOverrideConfig:
    return RuntimeOverrideConfig(
        output_dir=Path(os.getenv("RUNTIME_OVERRIDE_OUTPUT_DIR", "artifacts/config")),
        require_human_approval_for_live=env_bool("RUNTIME_OVERRIDE_REQUIRE_HUMAN_APPROVAL_FOR_LIVE", True),
        block_protected_keys=env_bool("RUNTIME_OVERRIDE_BLOCK_PROTECTED_KEYS", True),
        max_ttl_minutes=env_int("RUNTIME_OVERRIDE_MAX_TTL_MINUTES", 60),
    )


def key_is_protected(key: str, config: RuntimeOverrideConfig) -> bool:
    normalized = key.strip().lower()

    return any(pattern in normalized for pattern in config.protected_key_patterns)


def evaluate_runtime_override(
    *,
    request: RuntimeOverrideRequest | dict[str, Any],
    config: RuntimeOverrideConfig | None = None,
) -> RuntimeOverrideDecision:
    resolved_config = config or load_runtime_override_config()
    parsed = request if isinstance(request, RuntimeOverrideRequest) else RuntimeOverrideRequest.model_validate(request)

    blockers: list[str] = []
    warnings: list[str] = []

    protected = key_is_protected(parsed.key, resolved_config)

    if resolved_config.block_protected_keys and protected and not parsed.emergency_change:
        blockers.append("protected_key_override_blocked")

    if parsed.environment in {"production", "live"} and resolved_config.require_human_approval_for_live:
        if not parsed.human_approval_valid:
            blockers.append("human_approval_required_for_live_override")

        if not parsed.approved_by:
            blockers.append("approved_by_missing_for_live_override")

    if parsed.ttl_minutes > resolved_config.max_ttl_minutes:
        blockers.append("override_ttl_above_limit")

    if not parsed.reason.strip():
        blockers.append("override_reason_missing")

    if parsed.emergency_change:
        warnings.append("emergency_override_requires_post_review")

    approved = not blockers

    return RuntimeOverrideDecision(
        override_id=parsed.override_id,
        key=parsed.key,
        status="APPROVED" if approved and not warnings else "WARN" if approved else "BLOCKED",
        approved=approved,
        blockers=blockers,
        warnings=warnings,
        request=parsed.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_runtime_override_decision(
    decision: RuntimeOverrideDecision,
    *,
    output_dir: str | Path | None = None,
    name: str = "runtime_override_decision_latest",
) -> Path:
    config = load_runtime_override_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path