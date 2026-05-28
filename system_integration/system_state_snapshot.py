from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from system_integration.error_taxonomy import SystemBlockerReport, aggregate_system_blockers
from system_integration.runtime_context import IntegratedRuntimeContext
from system_integration.system_state_machine import SystemStateMachineState


load_dotenv()


SnapshotStatus = Literal["PASS", "WARN", "FAIL"]


class UnifiedSystemStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "unified_system_state_snapshot"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: SnapshotStatus
    healthy: bool

    runtime_context: dict[str, Any]
    system_state: dict[str, Any]

    blockers_report: dict[str, Any]

    signal_pipeline: dict[str, Any] | None = None
    sentiment_journal: dict[str, Any] | None = None
    portfolio_live_ops: dict[str, Any] | None = None
    execution_contract: dict[str, Any] | None = None

    observability: dict[str, Any] = Field(default_factory=dict)
    storage: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_unified_system_state_snapshot(
    *,
    runtime_context: IntegratedRuntimeContext | dict[str, Any],
    system_state: SystemStateMachineState | dict[str, Any],
    blockers: list[Any] | None = None,
    signal_pipeline: dict[str, Any] | None = None,
    sentiment_journal: dict[str, Any] | None = None,
    portfolio_live_ops: dict[str, Any] | None = None,
    execution_contract: dict[str, Any] | None = None,
    observability: dict[str, Any] | None = None,
    storage: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> UnifiedSystemStateSnapshot:
    parsed_context = runtime_context if isinstance(runtime_context, IntegratedRuntimeContext) else IntegratedRuntimeContext.model_validate(runtime_context)
    parsed_state = system_state if isinstance(system_state, SystemStateMachineState) else SystemStateMachineState.model_validate(system_state)

    collected_blockers = list(blockers or [])

    if parsed_context.kill_switch_active:
        collected_blockers.append("runtime_context_kill_switch_active")

    if parsed_state.state in {"BLOCKED", "KILL_SWITCH_ACTIVE"}:
        collected_blockers.append(f"system_state_{parsed_state.state.lower()}")

    blockers_report = aggregate_system_blockers(blockers=collected_blockers) if collected_blockers else aggregate_system_blockers(blockers=[])

    healthy = blockers_report.passed and parsed_state.state not in {"BLOCKED", "KILL_SWITCH_ACTIVE"}

    warnings_present = bool(blockers_report.warning_count or blockers_report.info_count)

    return UnifiedSystemStateSnapshot(
        status="PASS" if healthy and not warnings_present else "WARN" if healthy else "FAIL",
        healthy=healthy,
        runtime_context=parsed_context.model_dump(mode="json"),
        system_state=parsed_state.model_dump(mode="json"),
        blockers_report=blockers_report.model_dump(mode="json"),
        signal_pipeline=signal_pipeline,
        sentiment_journal=sentiment_journal,
        portfolio_live_ops=portfolio_live_ops,
        execution_contract=execution_contract,
        observability=observability or {},
        storage=storage or {},
        metadata=metadata or {},
    )


def export_unified_system_state_snapshot(
    snapshot: UnifiedSystemStateSnapshot,
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or os.getenv("SYSTEM_STATE_SNAPSHOT_FILE", "artifacts/system_integration/unified_system_state_snapshot.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path