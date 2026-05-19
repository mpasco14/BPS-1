"""
Emergency shutdown / safe mode.

Responsabilidades:
- Ativar modo seguro operacional.
- Bloquear novas entradas.
- Cancelar ordens abertas quando fornecidas.
- Gerar relatório auditável.
- Persistir estado local de safe mode.

Este módulo NÃO força fechamento de posição.
Nesta fase, ele cancela ordens abertas e bloqueia novas entradas.
Fechamento forçado de posição deve ser tratado em etapa separada e com extremo cuidado.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from execution.binance_futures_client import BinanceFuturesConfig, BinanceFuturesRestClient
from execution.cancel_order import CancelDecision, OpenOrderState, cancel_order_if_needed


load_dotenv()


ShutdownStatus = Literal["SAFE_MODE_ACTIVE", "DRY_RUN", "FAILED"]


class EmergencyShutdownConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True

    output_dir: Path = Path("artifacts/ops")
    state_file: Path = Path("artifacts/ops/emergency_shutdown_state.json")

    dry_run: bool = True
    block_new_entries: bool = True
    cancel_open_orders: bool = True

    default_reason: str = "manual_operator_request"


class SafeModeState(BaseModel):
    model_config = ConfigDict(extra="allow")

    safe_mode_active: bool = True
    new_entries_blocked: bool = True
    kill_switch_reason: str

    activated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    activated_by: str = "operator"

    metadata: dict[str, Any] = Field(default_factory=dict)


class EmergencyActionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: str
    attempted: bool
    success: bool

    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class EmergencyShutdownReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "emergency_shutdown"
    status: ShutdownStatus

    reason: str
    dry_run: bool

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    safe_mode_state: dict[str, Any]
    actions: list[dict[str, Any]] = Field(default_factory=list)

    open_orders_received: int = 0
    cancel_attempts: int = 0
    cancel_successes: int = 0
    cancel_failures: int = 0

    passed: bool = True


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_emergency_shutdown_config() -> EmergencyShutdownConfig:
    return EmergencyShutdownConfig(
        enabled=env_bool("EMERGENCY_SHUTDOWN_ENABLED", True),
        output_dir=Path(os.getenv("EMERGENCY_SHUTDOWN_OUTPUT_DIR", "artifacts/ops")),
        state_file=Path(os.getenv("EMERGENCY_SHUTDOWN_STATE_FILE", "artifacts/ops/emergency_shutdown_state.json")),
        dry_run=env_bool("EMERGENCY_SHUTDOWN_DRY_RUN", True),
        block_new_entries=env_bool("EMERGENCY_SHUTDOWN_BLOCK_NEW_ENTRIES", True),
        cancel_open_orders=env_bool("EMERGENCY_SHUTDOWN_CANCEL_OPEN_ORDERS", True),
        default_reason=os.getenv("EMERGENCY_SHUTDOWN_DEFAULT_REASON", "manual_operator_request"),
    )


def build_safe_mode_state(
    *,
    reason: str,
    block_new_entries: bool = True,
    activated_by: str = "operator",
    metadata: dict[str, Any] | None = None,
) -> SafeModeState:
    return SafeModeState(
        safe_mode_active=True,
        new_entries_blocked=block_new_entries,
        kill_switch_reason=reason,
        activated_by=activated_by,
        metadata=metadata or {},
    )


def persist_safe_mode_state(
    state: SafeModeState,
    *,
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def load_safe_mode_state(path: str | Path) -> SafeModeState | None:
    input_path = Path(path)

    if not input_path.exists():
        return None

    payload = json.loads(input_path.read_text(encoding="utf-8"))

    return SafeModeState.model_validate(payload)


def clear_safe_mode_state(path: str | Path) -> bool:
    input_path = Path(path)

    if not input_path.exists():
        return False

    input_path.unlink()

    return True


def normalize_open_order(order: OpenOrderState | dict[str, Any]) -> OpenOrderState:
    if isinstance(order, OpenOrderState):
        return order

    return OpenOrderState.model_validate(order)


def force_cancel_decision(order: OpenOrderState, reason: str) -> CancelDecision:
    return CancelDecision(
        should_cancel=True,
        reasons=["kill_switch_active"],
        details=[f"emergency_shutdown:{reason}"],
        order=order.model_dump(mode="json"),
    )


def build_paper_client() -> BinanceFuturesRestClient:
    return BinanceFuturesRestClient(
        config=BinanceFuturesConfig(execution_mode="paper")
    )


def cancel_orders_for_shutdown(
    *,
    open_orders: list[OpenOrderState | dict[str, Any]],
    reason: str,
    client: BinanceFuturesRestClient | None = None,
    dry_run: bool = True,
) -> list[EmergencyActionResult]:
    results: list[EmergencyActionResult] = []

    for raw_order in open_orders:
        order = normalize_open_order(raw_order)
        decision = force_cancel_decision(order, reason)

        if dry_run:
            results.append(
                EmergencyActionResult(
                    action="cancel_open_order",
                    attempted=False,
                    success=True,
                    message="dry_run_cancel_skipped",
                    payload={
                        "order": order.model_dump(mode="json"),
                        "decision": decision.model_dump(mode="json"),
                    },
                )
            )
            continue

        cancel_result = cancel_order_if_needed(
            order=order,
            decision=decision,
            client=client or build_paper_client(),
        )

        results.append(
            EmergencyActionResult(
                action="cancel_open_order",
                attempted=cancel_result.attempted,
                success=cancel_result.cancelled,
                message="cancelled" if cancel_result.cancelled else "cancel_failed",
                payload={
                    "order": order.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
                    "cancel_result": cancel_result.model_dump(mode="json"),
                },
                error=cancel_result.error,
            )
        )

    return results


def execute_emergency_shutdown(
    *,
    open_orders: list[OpenOrderState | dict[str, Any]] | None = None,
    reason: str | None = None,
    config: EmergencyShutdownConfig | None = None,
    client: BinanceFuturesRestClient | None = None,
    dry_run: bool | None = None,
    activated_by: str = "operator",
) -> EmergencyShutdownReport:
    resolved_config = config or load_emergency_shutdown_config()
    resolved_reason = reason or resolved_config.default_reason
    resolved_dry_run = resolved_config.dry_run if dry_run is None else dry_run

    orders = open_orders or []

    if not resolved_config.enabled:
        state = build_safe_mode_state(
            reason=resolved_reason,
            block_new_entries=False,
            activated_by=activated_by,
            metadata={"enabled": False},
        )

        return EmergencyShutdownReport(
            status="FAILED",
            reason=resolved_reason,
            dry_run=resolved_dry_run,
            safe_mode_state=state.model_dump(mode="json"),
            actions=[
                EmergencyActionResult(
                    action="emergency_shutdown",
                    attempted=False,
                    success=False,
                    message="emergency_shutdown_disabled",
                ).model_dump(mode="json")
            ],
            open_orders_received=len(orders),
            passed=False,
        )

    state = build_safe_mode_state(
        reason=resolved_reason,
        block_new_entries=resolved_config.block_new_entries,
        activated_by=activated_by,
        metadata={
            "dry_run": resolved_dry_run,
            "cancel_open_orders": resolved_config.cancel_open_orders,
        },
    )

    actions: list[EmergencyActionResult] = []

    state_path = persist_safe_mode_state(
        state,
        path=resolved_config.state_file,
    )

    actions.append(
        EmergencyActionResult(
            action="activate_safe_mode",
            attempted=True,
            success=True,
            message="safe_mode_state_persisted",
            payload={"path": str(state_path)},
        )
    )

    cancel_results: list[EmergencyActionResult] = []

    if resolved_config.cancel_open_orders:
        cancel_results = cancel_orders_for_shutdown(
            open_orders=orders,
            reason=resolved_reason,
            client=client,
            dry_run=resolved_dry_run,
        )
        actions.extend(cancel_results)
    else:
        actions.append(
            EmergencyActionResult(
                action="cancel_open_orders",
                attempted=False,
                success=True,
                message="cancel_open_orders_disabled_by_config",
            )
        )

    cancel_attempts = sum(1 for item in cancel_results if item.attempted)
    cancel_successes = sum(1 for item in cancel_results if item.success)
    cancel_failures = sum(1 for item in cancel_results if item.attempted and not item.success)

    passed = all(item.success for item in actions)

    return EmergencyShutdownReport(
        status="DRY_RUN" if resolved_dry_run else "SAFE_MODE_ACTIVE",
        reason=resolved_reason,
        dry_run=resolved_dry_run,
        safe_mode_state=state.model_dump(mode="json"),
        actions=[item.model_dump(mode="json") for item in actions],
        open_orders_received=len(orders),
        cancel_attempts=cancel_attempts,
        cancel_successes=cancel_successes,
        cancel_failures=cancel_failures,
        passed=passed,
    )


def export_emergency_shutdown_report(
    report: EmergencyShutdownReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "emergency_shutdown_latest",
) -> Path:
    config = load_emergency_shutdown_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path


def emergency_shutdown_report_to_dict(report: EmergencyShutdownReport) -> dict[str, Any]:
    return report.model_dump(mode="json")