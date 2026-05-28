from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


SystemState = Literal[
    "BOOTING",
    "CONFIG_VALIDATION",
    "PAPER_READY",
    "TESTNET_READY",
    "LIVE_PREFLIGHT",
    "MICRO_LIVE_READY",
    "RUNNING",
    "SAFE_MODE",
    "KILL_SWITCH_ACTIVE",
    "PAUSED",
    "STOPPED",
    "BLOCKED",
]

StateTransitionAction = Literal[
    "BOOT",
    "VALIDATE_CONFIG",
    "MARK_PAPER_READY",
    "MARK_TESTNET_READY",
    "START_LIVE_PREFLIGHT",
    "MARK_MICRO_LIVE_READY",
    "START_RUNNING",
    "ENTER_SAFE_MODE",
    "ACTIVATE_KILL_SWITCH",
    "PAUSE",
    "RESUME",
    "STOP",
    "BLOCK",
    "RESET_TO_CONFIG_VALIDATION",
]


class SystemStateMachineState(BaseModel):
    model_config = ConfigDict(extra="allow")

    state: SystemState = "BOOTING"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: StateTransitionAction
    requested_by: str = "system"
    reason: str | None = None

    config_valid: bool = False
    paper_validated: bool = False
    testnet_validated: bool = False
    live_preflight_passed: bool = False
    production_guard_passed: bool = False
    emergency_test_passed: bool = False
    human_approval_valid: bool = False
    kill_switch_clear: bool = True
    safe_mode_clear: bool = True

    metadata: dict[str, Any] = Field(default_factory=dict)


class StateTransitionDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "system_state_machine"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    approved: bool
    action: StateTransitionAction
    state_before: SystemState
    state_after: SystemState

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    request: dict[str, Any]
    resulting_state: dict[str, Any]


ACTION_TARGETS: dict[str, SystemState] = {
    "BOOT": "BOOTING",
    "VALIDATE_CONFIG": "CONFIG_VALIDATION",
    "MARK_PAPER_READY": "PAPER_READY",
    "MARK_TESTNET_READY": "TESTNET_READY",
    "START_LIVE_PREFLIGHT": "LIVE_PREFLIGHT",
    "MARK_MICRO_LIVE_READY": "MICRO_LIVE_READY",
    "START_RUNNING": "RUNNING",
    "ENTER_SAFE_MODE": "SAFE_MODE",
    "ACTIVATE_KILL_SWITCH": "KILL_SWITCH_ACTIVE",
    "PAUSE": "PAUSED",
    "RESUME": "RUNNING",
    "STOP": "STOPPED",
    "BLOCK": "BLOCKED",
    "RESET_TO_CONFIG_VALIDATION": "CONFIG_VALIDATION",
}


ALLOWED_TRANSITIONS: dict[str, set[SystemState]] = {
    "BOOTING": {"CONFIG_VALIDATION", "BLOCKED", "STOPPED"},
    "CONFIG_VALIDATION": {"PAPER_READY", "BLOCKED", "STOPPED"},
    "PAPER_READY": {"RUNNING", "TESTNET_READY", "BLOCKED", "STOPPED"},
    "TESTNET_READY": {"RUNNING", "LIVE_PREFLIGHT", "BLOCKED", "STOPPED"},
    "LIVE_PREFLIGHT": {"MICRO_LIVE_READY", "BLOCKED", "STOPPED"},
    "MICRO_LIVE_READY": {"RUNNING", "SAFE_MODE", "BLOCKED", "STOPPED"},
    "RUNNING": {"PAUSED", "SAFE_MODE", "KILL_SWITCH_ACTIVE", "BLOCKED", "STOPPED"},
    "SAFE_MODE": {"PAUSED", "RUNNING", "KILL_SWITCH_ACTIVE", "STOPPED", "BLOCKED"},
    "KILL_SWITCH_ACTIVE": {"STOPPED", "CONFIG_VALIDATION", "BLOCKED"},
    "PAUSED": {"RUNNING", "SAFE_MODE", "STOPPED", "BLOCKED"},
    "STOPPED": {"CONFIG_VALIDATION", "BOOTING"},
    "BLOCKED": {"CONFIG_VALIDATION", "STOPPED"},
}


def initial_system_state() -> SystemStateMachineState:
    initial = os.getenv("SYSTEM_STATE_INITIAL", "BOOTING").strip().upper()

    if initial in ACTION_TARGETS.values():
        return SystemStateMachineState(state=initial)  # type: ignore[arg-type]

    return SystemStateMachineState(state="BOOTING")


def evaluate_state_transition(
    *,
    current: SystemStateMachineState | dict[str, Any],
    request: StateTransitionRequest | dict[str, Any],
) -> StateTransitionDecision:
    parsed_current = current if isinstance(current, SystemStateMachineState) else SystemStateMachineState.model_validate(current)
    parsed_request = request if isinstance(request, StateTransitionRequest) else StateTransitionRequest.model_validate(request)

    target = ACTION_TARGETS[parsed_request.action]
    blockers: list[str] = []
    warnings: list[str] = []

    allowed_targets = ALLOWED_TRANSITIONS.get(parsed_current.state, set())

    if target not in allowed_targets and target != parsed_current.state:
        blockers.append("transition_not_allowed_from_current_state")

    if target == "PAPER_READY" and not parsed_request.config_valid:
        blockers.append("config_validation_required_for_paper_ready")

    if target == "TESTNET_READY" and not parsed_request.paper_validated:
        blockers.append("paper_validation_required_for_testnet_ready")

    if target == "LIVE_PREFLIGHT" and not parsed_request.testnet_validated:
        blockers.append("testnet_validation_required_for_live_preflight")

    if target == "MICRO_LIVE_READY":
        if not parsed_request.live_preflight_passed:
            blockers.append("live_preflight_required")
        if not parsed_request.production_guard_passed:
            blockers.append("production_guard_required")
        if not parsed_request.emergency_test_passed:
            blockers.append("emergency_test_required")
        if not parsed_request.human_approval_valid:
            blockers.append("human_approval_required")

    if target == "RUNNING":
        if not parsed_request.kill_switch_clear:
            blockers.append("kill_switch_must_be_clear_to_run")
        if not parsed_request.safe_mode_clear and parsed_current.state != "SAFE_MODE":
            blockers.append("safe_mode_must_be_clear_to_run")

    if target == "CONFIG_VALIDATION" and parsed_current.state == "KILL_SWITCH_ACTIVE":
        if not parsed_request.human_approval_valid:
            blockers.append("human_approval_required_to_reset_from_kill_switch")
        if not parsed_request.kill_switch_clear:
            blockers.append("kill_switch_clearance_required")

    if target in {"SAFE_MODE", "KILL_SWITCH_ACTIVE", "BLOCKED"} and not parsed_request.reason:
        warnings.append("reason_recommended_for_protective_state")

    approved = not blockers
    next_state = parsed_current

    if approved:
        next_state = SystemStateMachineState(
            state=target,
            reason=parsed_request.reason,
            metadata={
                **parsed_current.metadata,
                **parsed_request.metadata,
                "last_action": parsed_request.action,
                "requested_by": parsed_request.requested_by,
            },
        )

    return StateTransitionDecision(
        approved=approved,
        action=parsed_request.action,
        state_before=parsed_current.state,
        state_after=next_state.state if approved else parsed_current.state,
        blockers=blockers,
        warnings=warnings,
        request=parsed_request.model_dump(mode="json"),
        resulting_state=next_state.model_dump(mode="json"),
    )


def export_state_transition_decision(
    decision: StateTransitionDecision,
    *,
    output_dir: str | Path | None = None,
    name: str = "state_transition_latest",
) -> Path:
    path = Path(output_dir or os.getenv("SYSTEM_STATE_OUTPUT_DIR", "artifacts/system_integration"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path