from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


OperatorCommand = Literal[
    "STATUS",
    "ENTER_SAFE_MODE",
    "EXIT_SAFE_MODE",
    "ACTIVATE_KILL_SWITCH",
    "RESET_KILL_SWITCH",
    "START_SESSION",
    "STOP_SESSION",
    "PAUSE_TRADING",
    "RESUME_TRADING",
]

CommandTarget = Literal[
    "console",
    "safe_mode",
    "kill_switch",
    "session_supervisor",
    "trading_control",
]


PROTECTED_COMMANDS = {
    "EXIT_SAFE_MODE",
    "RESET_KILL_SWITCH",
    "START_SESSION",
    "RESUME_TRADING",
}


class OperatorConsoleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live_ops")

    require_approval_for_protected: bool = True
    require_reason: bool = True


class OperatorCommandRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    command_id: str
    command: OperatorCommand

    operator: str = "operator"
    environment: str = "development"
    session_name: str | None = None

    reason: str | None = None

    human_approval_valid: bool = False
    approved_by: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class OperatorCommandDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "operator_command_console"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    command_id: str
    command: OperatorCommand
    target: CommandTarget

    approved: bool
    protected: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    routed_payload: dict[str, Any] = Field(default_factory=dict)

    request: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_operator_console_config() -> OperatorConsoleConfig:
    return OperatorConsoleConfig(
        output_dir=Path(os.getenv("OPERATOR_CONSOLE_OUTPUT_DIR", "artifacts/live_ops")),
        require_approval_for_protected=env_bool("OPERATOR_CONSOLE_REQUIRE_APPROVAL_FOR_PROTECTED", True),
        require_reason=env_bool("OPERATOR_CONSOLE_REQUIRE_REASON", True),
    )


def target_for_command(command: OperatorCommand) -> CommandTarget:
    if command in {"ENTER_SAFE_MODE", "EXIT_SAFE_MODE"}:
        return "safe_mode"

    if command in {"ACTIVATE_KILL_SWITCH", "RESET_KILL_SWITCH"}:
        return "kill_switch"

    if command in {"START_SESSION", "STOP_SESSION"}:
        return "session_supervisor"

    if command in {"PAUSE_TRADING", "RESUME_TRADING"}:
        return "trading_control"

    return "console"


def build_routed_payload(request: OperatorCommandRequest, target: CommandTarget) -> dict[str, Any]:
    base = {
        "operator": request.operator,
        "reason": request.reason,
        "environment": request.environment,
        "session_name": request.session_name,
        "human_approval_valid": request.human_approval_valid,
        "approved_by": request.approved_by,
        "metadata": request.metadata,
    }

    if target == "safe_mode":
        return {
            **base,
            "action": request.command,
        }

    if target == "kill_switch":
        mapped = {
            "ACTIVATE_KILL_SWITCH": "ACTIVATE",
            "RESET_KILL_SWITCH": "RESET",
        }

        return {
            **base,
            "command": mapped.get(request.command, "STATUS"),
        }

    return {
        **base,
        "command": request.command,
    }


def evaluate_operator_command(
    *,
    request: OperatorCommandRequest | dict[str, Any],
    config: OperatorConsoleConfig | None = None,
) -> OperatorCommandDecision:
    resolved_config = config or load_operator_console_config()
    parsed = request if isinstance(request, OperatorCommandRequest) else OperatorCommandRequest.model_validate(request)

    blockers: list[str] = []
    warnings: list[str] = []

    protected = parsed.command in PROTECTED_COMMANDS
    target = target_for_command(parsed.command)

    if resolved_config.require_reason and parsed.command != "STATUS" and not parsed.reason:
        blockers.append("command_reason_required")

    if protected and resolved_config.require_approval_for_protected:
        if not parsed.human_approval_valid:
            blockers.append("human_approval_required_for_protected_command")

        if not parsed.approved_by:
            blockers.append("approved_by_required_for_protected_command")

    if parsed.environment in {"production", "live"} and parsed.command in {"START_SESSION", "RESUME_TRADING"}:
        warnings.append("live_environment_command_requires_extra_review")

    if parsed.command == "ACTIVATE_KILL_SWITCH":
        blockers = [item for item in blockers if item != "command_reason_required"]
        warnings.append("kill_switch_activation_allowed_even_without_reason")

    approved = not blockers

    return OperatorCommandDecision(
        command_id=parsed.command_id,
        command=parsed.command,
        target=target,
        approved=approved,
        protected=protected,
        blockers=blockers,
        warnings=warnings,
        routed_payload=build_routed_payload(parsed, target),
        request=parsed.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_operator_command_decision(
    decision: OperatorCommandDecision,
    *,
    output_dir: str | Path | None = None,
    name: str = "operator_command_decision_latest",
) -> Path:
    config = load_operator_console_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path