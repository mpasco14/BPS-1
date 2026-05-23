from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


EmergencyStepStatus = Literal["PASS", "FAIL", "WARN"]


class EmergencyStopProcedureConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/production")

    require_cancel_all: bool = True
    require_new_orders_blocked: bool = True
    require_safe_mode: bool = True
    require_notification: bool = True


class EmergencyStopProcedureInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    kill_switch_activated: bool = False
    cancel_all_orders_called: bool = False
    open_orders_after_cancel: int = 0
    new_orders_blocked: bool = False
    safe_mode_active: bool = False
    notification_sent: bool = False
    positions_left_to_manage: int = 0


class EmergencyStopStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: EmergencyStepStatus
    message: str
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class EmergencyStopProcedureReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "emergency_stop_procedure_test"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: EmergencyStepStatus

    steps_count: int
    pass_count: int
    fail_count: int
    warn_count: int
    blocking_fail_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    steps: list[dict[str, Any]] = Field(default_factory=list)
    inputs: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_emergency_stop_procedure_config() -> EmergencyStopProcedureConfig:
    return EmergencyStopProcedureConfig(
        output_dir=Path(os.getenv("EMERGENCY_STOP_TEST_OUTPUT_DIR", "artifacts/production")),
        require_cancel_all=env_bool("EMERGENCY_STOP_REQUIRE_CANCEL_ALL", True),
        require_new_orders_blocked=env_bool("EMERGENCY_STOP_REQUIRE_NEW_ORDERS_BLOCKED", True),
        require_safe_mode=env_bool("EMERGENCY_STOP_REQUIRE_SAFE_MODE", True),
        require_notification=env_bool("EMERGENCY_STOP_REQUIRE_NOTIFICATION", True),
    )


def step(
    code: str,
    ok: bool,
    message: str,
    *,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = True,
) -> EmergencyStopStep:
    return EmergencyStopStep(
        code=code if ok else f"{code}_FAILED",
        status="PASS" if ok else "FAIL",
        message=message,
        value=value,
        expected=expected,
        blocking=not ok and blocking,
    )


def build_emergency_stop_procedure_report(
    *,
    inputs: EmergencyStopProcedureInputs | dict[str, Any],
    config: EmergencyStopProcedureConfig | None = None,
) -> EmergencyStopProcedureReport:
    resolved_config = config or load_emergency_stop_procedure_config()
    resolved_inputs = inputs if isinstance(inputs, EmergencyStopProcedureInputs) else EmergencyStopProcedureInputs.model_validate(inputs)

    steps: list[EmergencyStopStep] = []

    steps.append(
        step(
            "KILL_SWITCH_ACTIVATED",
            resolved_inputs.kill_switch_activated,
            "Kill switch precisa ser ativado.",
            value=resolved_inputs.kill_switch_activated,
            expected=True,
        )
    )

    if resolved_config.require_cancel_all:
        steps.append(
            step(
                "CANCEL_ALL_ORDERS_CALLED",
                resolved_inputs.cancel_all_orders_called,
                "Cancelamento de todas as ordens precisa ser chamado.",
                value=resolved_inputs.cancel_all_orders_called,
                expected=True,
            )
        )

        steps.append(
            step(
                "NO_OPEN_ORDERS_AFTER_CANCEL",
                resolved_inputs.open_orders_after_cancel == 0,
                "Após cancelamento, não deve haver ordens abertas.",
                value=resolved_inputs.open_orders_after_cancel,
                expected=0,
            )
        )

    if resolved_config.require_new_orders_blocked:
        steps.append(
            step(
                "NEW_ORDERS_BLOCKED",
                resolved_inputs.new_orders_blocked,
                "Novas ordens precisam ficar bloqueadas.",
                value=resolved_inputs.new_orders_blocked,
                expected=True,
            )
        )

    if resolved_config.require_safe_mode:
        steps.append(
            step(
                "SAFE_MODE_ACTIVE",
                resolved_inputs.safe_mode_active,
                "Safe mode precisa estar ativo.",
                value=resolved_inputs.safe_mode_active,
                expected=True,
            )
        )

    if resolved_config.require_notification:
        steps.append(
            step(
                "NOTIFICATION_SENT",
                resolved_inputs.notification_sent,
                "Notificação de emergência precisa ser enviada.",
                value=resolved_inputs.notification_sent,
                expected=True,
                blocking=False,
            )
        )

    if resolved_inputs.positions_left_to_manage > 0:
        steps.append(
            EmergencyStopStep(
                code="POSITIONS_LEFT_TO_MANAGE",
                status="WARN",
                message="Existem posições abertas para gestão manual/controlada.",
                value=resolved_inputs.positions_left_to_manage,
                expected=0,
                blocking=False,
            )
        )

    pass_count = sum(1 for item in steps if item.status == "PASS")
    fail_count = sum(1 for item in steps if item.status == "FAIL")
    warn_count = sum(1 for item in steps if item.status == "WARN")
    blocking_fail_count = sum(1 for item in steps if item.blocking)

    blockers = [item.code for item in steps if item.blocking]
    warnings = [item.code for item in steps if item.status == "WARN"]

    passed = blocking_fail_count == 0

    return EmergencyStopProcedureReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        steps_count=len(steps),
        pass_count=pass_count,
        fail_count=fail_count,
        warn_count=warn_count,
        blocking_fail_count=blocking_fail_count,
        blockers=blockers,
        warnings=warnings,
        steps=[item.model_dump(mode="json") for item in steps],
        inputs=resolved_inputs.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_emergency_stop_procedure_report(
    report: EmergencyStopProcedureReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "emergency_stop_procedure_latest",
) -> Path:
    config = load_emergency_stop_procedure_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path