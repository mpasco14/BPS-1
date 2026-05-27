from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


SafeModeStatus = Literal["ACTIVE", "INACTIVE"]
SafeModeAction = Literal["ENTER_SAFE_MODE", "EXIT_SAFE_MODE", "STATUS"]


class SafeModeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live_ops")

    require_approval_to_exit: bool = True
    block_new_orders: bool = True
    allow_reduce_only: bool = True


class SafeModeState(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: SafeModeStatus = "INACTIVE"
    activated_at: datetime | None = None
    activated_by: str | None = None
    reason: str | None = None

    block_new_orders: bool = True
    allow_reduce_only: bool = True

    metadata: dict[str, Any] = Field(default_factory=dict)


class SafeModeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: SafeModeAction
    operator: str = "operator"
    reason: str | None = None
    human_approval_valid: bool = False
    approved_by: str | None = None


class SafeModeDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "safe_mode_controller"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    action: SafeModeAction
    approved: bool
    status_before: SafeModeStatus
    status_after: SafeModeStatus

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    state: dict[str, Any]
    request: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_safe_mode_config() -> SafeModeConfig:
    return SafeModeConfig(
        output_dir=Path(os.getenv("SAFE_MODE_OUTPUT_DIR", "artifacts/live_ops")),
        require_approval_to_exit=env_bool("SAFE_MODE_REQUIRE_APPROVAL_TO_EXIT", True),
        block_new_orders=env_bool("SAFE_MODE_BLOCK_NEW_ORDERS", True),
        allow_reduce_only=env_bool("SAFE_MODE_ALLOW_REDUCE_ONLY", True),
    )


def evaluate_safe_mode_request(
    *,
    state: SafeModeState | dict[str, Any] | None = None,
    request: SafeModeRequest | dict[str, Any],
    config: SafeModeConfig | None = None,
) -> SafeModeDecision:
    resolved_config = config or load_safe_mode_config()
    current_state = SafeModeState() if state is None else state if isinstance(state, SafeModeState) else SafeModeState.model_validate(state)
    parsed_request = request if isinstance(request, SafeModeRequest) else SafeModeRequest.model_validate(request)

    blockers: list[str] = []
    warnings: list[str] = []

    status_before = current_state.status
    next_state = current_state

    if parsed_request.action == "STATUS":
        return SafeModeDecision(
            action=parsed_request.action,
            approved=True,
            status_before=status_before,
            status_after=current_state.status,
            state=current_state.model_dump(mode="json"),
            request=parsed_request.model_dump(mode="json"),
            config=resolved_config.model_dump(mode="json"),
        )

    if parsed_request.action == "ENTER_SAFE_MODE":
        if not parsed_request.reason:
            warnings.append("safe_mode_reason_missing")

        next_state = SafeModeState(
            status="ACTIVE",
            activated_at=datetime.now(timezone.utc),
            activated_by=parsed_request.operator,
            reason=parsed_request.reason,
            block_new_orders=resolved_config.block_new_orders,
            allow_reduce_only=resolved_config.allow_reduce_only,
            metadata=current_state.metadata,
        )

    if parsed_request.action == "EXIT_SAFE_MODE":
        if resolved_config.require_approval_to_exit and not parsed_request.human_approval_valid:
            blockers.append("human_approval_required_to_exit_safe_mode")

        if resolved_config.require_approval_to_exit and not parsed_request.approved_by:
            blockers.append("approved_by_required_to_exit_safe_mode")

        if not blockers:
            next_state = SafeModeState(
                status="INACTIVE",
                block_new_orders=False,
                allow_reduce_only=True,
                metadata={
                    **current_state.metadata,
                    "last_exit_by": parsed_request.operator,
                    "last_exit_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    approved = not blockers

    return SafeModeDecision(
        action=parsed_request.action,
        approved=approved,
        status_before=status_before,
        status_after=next_state.status if approved else current_state.status,
        blockers=blockers,
        warnings=warnings,
        state=(next_state if approved else current_state).model_dump(mode="json"),
        request=parsed_request.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_safe_mode_decision(
    decision: SafeModeDecision,
    *,
    output_dir: str | Path | None = None,
    name: str = "safe_mode_decision_latest",
) -> Path:
    config = load_safe_mode_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path