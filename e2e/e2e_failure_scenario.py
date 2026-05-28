from __future__ import annotations

from typing import Any, Literal

from e2e.e2e_models import E2EScenarioReport, load_e2e_config
from system_integration.execution_contract import RiskApprovalDecision
from system_integration.runtime_context import build_integrated_runtime_context
from system_integration.signal_risk_execution_adapter import SignalDecision, adapt_signal_to_risk_execution
from system_integration.system_state_machine import SystemStateMachineState
from system_integration.system_state_snapshot import build_unified_system_state_snapshot


FailureMode = Literal[
    "low_confidence_signal",
    "risk_rejected",
    "kill_switch_context",
    "missing_risk_decision",
]


def run_e2e_failure_scenario(
    *,
    failure_mode: FailureMode = "low_confidence_signal",
    session_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> E2EScenarioReport:
    config = load_e2e_config()
    resolved_session = session_name or f"{config.session_name}_failure"

    kill_switch_active = failure_mode == "kill_switch_context"

    runtime = build_integrated_runtime_context(
        environment="paper",
        execution_mode="paper",
        session_name=resolved_session,
        operator="e2e",
        metadata={"scenario": "failure", "failure_mode": failure_mode},
    )

    if kill_switch_active:
        runtime = runtime.model_copy(update={"kill_switch_active": True})

    confidence = 0.20 if failure_mode == "low_confidence_signal" else 0.72
    risk_approved = failure_mode not in {"risk_rejected", "missing_risk_decision"}

    risk_decision = None
    if failure_mode != "missing_risk_decision":
        risk_decision = RiskApprovalDecision(
            approved=risk_approved,
            risk_score=0.95 if not risk_approved else 0.25,
            blockers=["risk_rejected_by_e2e_failure_mode"] if not risk_approved else [],
        )

    pipeline = adapt_signal_to_risk_execution(
        signal=SignalDecision(
            symbol=config.default_symbol,
            timeframe=config.default_timeframe,
            direction="BUY",
            probability=0.51,
            confidence=confidence,
            edge=0.02,
            suggested_quantity=0.001,
            suggested_price=60000,
            suggested_notional_usd=60,
            suggested_margin_usd=5,
            suggested_leverage=12,
            metadata={"scenario": "failure", "failure_mode": failure_mode},
        ),
        risk_decision=risk_decision or RiskApprovalDecision(approved=False, blockers=["risk_decision_missing"]),
        execution_mode="paper",
        live_submission_allowed=False,
        safe_mode_active=False,
        kill_switch_active=kill_switch_active,
    )

    expected_blockers = list(pipeline.blockers)

    if kill_switch_active:
        expected_blockers.append("runtime_context_kill_switch_active")

    snapshot = build_unified_system_state_snapshot(
        runtime_context=runtime,
        system_state=SystemStateMachineState(state="RUNNING"),
        blockers=expected_blockers,
        signal_pipeline=pipeline.model_dump(mode="json"),
        execution_contract=pipeline.execution_contract,
        metadata={
            "scenario": "failure",
            "failure_mode": failure_mode,
            "expected_blocked": True,
        },
    )

    expected_blocked = bool(expected_blockers) and not snapshot.healthy

    return E2EScenarioReport(
        scenario_name=f"e2e_failure_scenario_{failure_mode}",
        scenario_kind="failure",
        status="EXPECTED_BLOCKED" if expected_blocked else "FAIL",
        passed=expected_blocked,
        expected_blocked=True,
        blockers=expected_blockers,
        warnings=list(pipeline.warnings),
        recommendations=[
            "Failure scenario passed only if the system blocks the unsafe flow.",
            "If this scenario becomes approved unexpectedly, investigate immediately.",
        ],
        runtime_context=runtime.model_dump(mode="json"),
        system_state=SystemStateMachineState(state="RUNNING").model_dump(mode="json"),
        snapshot=snapshot.model_dump(mode="json"),
        components={
            "signal_pipeline": pipeline.model_dump(mode="json"),
            "failure_mode": failure_mode,
        },
        metadata=metadata or {},
    )