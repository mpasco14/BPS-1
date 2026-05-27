from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


KillSwitchCommand = Literal["ACTIVATE", "RESET", "STATUS"]
KillSwitchStepStatus = Literal["PENDING", "EXECUTED", "SKIPPED", "BLOCKED"]


class KillSwitchRouterConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live_ops")

    require_cancel_all: bool = True
    require_safe_mode: bool = True
    require_alert: bool = True
    require_human_approval_to_reset: bool = True


class KillSwitchState(BaseModel):
    model_config = ConfigDict(extra="allow")

    active: bool = False
    activated_at: datetime | None = None
    activated_by: str | None = None
    reason: str | None = None

    reset_at: datetime | None = None
    reset_by: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class KillSwitchRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    command: KillSwitchCommand
    operator: str = "operator"
    reason: str | None = None

    human_approval_valid: bool = False
    approved_by: str | None = None
    emergency_state_clear: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)


class KillSwitchRouteStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    step_id: str
    description: str
    status: KillSwitchStepStatus = "PENDING"
    required: bool = True


class KillSwitchRouteReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "kill_switch_command_router"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    command: KillSwitchCommand
    approved: bool

    active_before: bool
    active_after: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    steps: list[dict[str, Any]] = Field(default_factory=list)
    state: dict[str, Any]
    request: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_kill_switch_router_config() -> KillSwitchRouterConfig:
    return KillSwitchRouterConfig(
        output_dir=Path(os.getenv("KILL_SWITCH_ROUTER_OUTPUT_DIR", "artifacts/live_ops")),
        require_cancel_all=env_bool("KILL_SWITCH_REQUIRE_CANCEL_ALL", True),
        require_safe_mode=env_bool("KILL_SWITCH_REQUIRE_SAFE_MODE", True),
        require_alert=env_bool("KILL_SWITCH_REQUIRE_ALERT", True),
        require_human_approval_to_reset=env_bool("KILL_SWITCH_REQUIRE_HUMAN_APPROVAL_TO_RESET", True),
    )


def activation_steps(config: KillSwitchRouterConfig) -> list[KillSwitchRouteStep]:
    steps = [
        KillSwitchRouteStep(
            step_id="block_new_orders",
            description="Bloquear novas ordens imediatamente.",
            status="EXECUTED",
            required=True,
        )
    ]

    if config.require_cancel_all:
        steps.append(
            KillSwitchRouteStep(
                step_id="cancel_open_orders",
                description="Cancelar ordens abertas.",
                status="EXECUTED",
                required=True,
            )
        )

    if config.require_safe_mode:
        steps.append(
            KillSwitchRouteStep(
                step_id="enter_safe_mode",
                description="Ativar safe mode.",
                status="EXECUTED",
                required=True,
            )
        )

    if config.require_alert:
        steps.append(
            KillSwitchRouteStep(
                step_id="emit_operator_alert",
                description="Emitir alerta para operador.",
                status="EXECUTED",
                required=True,
            )
        )

    return steps


def route_kill_switch_command(
    *,
    state: KillSwitchState | dict[str, Any] | None = None,
    request: KillSwitchRequest | dict[str, Any],
    config: KillSwitchRouterConfig | None = None,
) -> KillSwitchRouteReport:
    resolved_config = config or load_kill_switch_router_config()
    current_state = KillSwitchState() if state is None else state if isinstance(state, KillSwitchState) else KillSwitchState.model_validate(state)
    parsed_request = request if isinstance(request, KillSwitchRequest) else KillSwitchRequest.model_validate(request)

    blockers: list[str] = []
    warnings: list[str] = []
    steps: list[KillSwitchRouteStep] = []

    active_before = current_state.active
    next_state = current_state

    if parsed_request.command == "STATUS":
        return KillSwitchRouteReport(
            command=parsed_request.command,
            approved=True,
            active_before=active_before,
            active_after=current_state.active,
            state=current_state.model_dump(mode="json"),
            request=parsed_request.model_dump(mode="json"),
            config=resolved_config.model_dump(mode="json"),
        )

    if parsed_request.command == "ACTIVATE":
        if not parsed_request.reason:
            warnings.append("kill_switch_activation_reason_missing")

        steps = activation_steps(resolved_config)

        next_state = KillSwitchState(
            active=True,
            activated_at=datetime.now(timezone.utc),
            activated_by=parsed_request.operator,
            reason=parsed_request.reason,
            metadata=parsed_request.metadata,
        )

    if parsed_request.command == "RESET":
        if resolved_config.require_human_approval_to_reset and not parsed_request.human_approval_valid:
            blockers.append("human_approval_required_to_reset_kill_switch")

        if resolved_config.require_human_approval_to_reset and not parsed_request.approved_by:
            blockers.append("approved_by_required_to_reset_kill_switch")

        if not parsed_request.emergency_state_clear:
            blockers.append("emergency_state_not_clear")

        if not blockers:
            steps = [
                KillSwitchRouteStep(
                    step_id="verify_no_open_orders",
                    description="Confirmar ausência de ordens abertas.",
                    status="EXECUTED",
                    required=True,
                ),
                KillSwitchRouteStep(
                    step_id="verify_risk_state_ok",
                    description="Confirmar risk state OK.",
                    status="EXECUTED",
                    required=True,
                ),
            ]

            next_state = KillSwitchState(
                active=False,
                reset_at=datetime.now(timezone.utc),
                reset_by=parsed_request.operator,
                metadata={
                    **current_state.metadata,
                    "reset_reason": parsed_request.reason,
                },
            )

    approved = not blockers

    return KillSwitchRouteReport(
        command=parsed_request.command,
        approved=approved,
        active_before=active_before,
        active_after=next_state.active if approved else current_state.active,
        blockers=blockers,
        warnings=warnings,
        steps=[item.model_dump(mode="json") for item in steps],
        state=(next_state if approved else current_state).model_dump(mode="json"),
        request=parsed_request.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_kill_switch_route_report(
    report: KillSwitchRouteReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "kill_switch_route_latest",
) -> Path:
    config = load_kill_switch_router_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path