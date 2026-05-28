from __future__ import annotations

from typing import Any

from e2e.e2e_models import E2EScenarioReport, load_e2e_config
from live_ops.kill_switch_router import KillSwitchRequest, KillSwitchState, route_kill_switch_command
from live_ops.live_session_supervisor import LiveSessionTelemetry, supervise_live_session
from live_ops.safe_mode_controller import SafeModeRequest, SafeModeState, evaluate_safe_mode_request
from system_integration.portfolio_live_ops_integration import (
    LiveOpsInput,
    PortfolioRiskInput,
    integrate_portfolio_risk_live_ops,
)
from system_integration.runtime_context import build_integrated_runtime_context
from system_integration.system_state_machine import (
    StateTransitionRequest,
    SystemStateMachineState,
    evaluate_state_transition,
)
from system_integration.system_state_snapshot import build_unified_system_state_snapshot


def run_e2e_kill_switch_scenario(
    *,
    session_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> E2EScenarioReport:
    config = load_e2e_config()
    resolved_session = session_name or f"{config.session_name}_kill_switch"

    runtime = build_integrated_runtime_context(
        environment="testnet",
        execution_mode="testnet",
        session_name=resolved_session,
        operator="e2e",
        metadata={"scenario": "kill_switch"},
    )
    runtime = runtime.model_copy(update={"kill_switch_active": True, "safe_mode_active": True})

    transition = evaluate_state_transition(
        current=SystemStateMachineState(state="RUNNING"),
        request=StateTransitionRequest(
            action="ACTIVATE_KILL_SWITCH",
            requested_by="e2e",
            reason="E2E kill switch scenario.",
        ),
    )

    safe_mode = evaluate_safe_mode_request(
        state=SafeModeState(status="INACTIVE"),
        request=SafeModeRequest(
            action="ENTER_SAFE_MODE",
            operator="e2e",
            reason="E2E kill switch activated safe mode.",
        ),
    )

    kill_switch = route_kill_switch_command(
        state=KillSwitchState(active=False),
        request=KillSwitchRequest(
            command="ACTIVATE",
            operator="e2e",
            reason="E2E kill switch activation.",
        ),
    )

    supervisor = supervise_live_session(
        telemetry=LiveSessionTelemetry(
            session_name=resolved_session,
            environment="testnet",
            kill_switch_active=True,
            safe_mode_active=True,
            open_orders_count=1,
            open_positions_count=1,
            drawdown_usd=1,
            rejection_rate=0.01,
            ood_rate=0.01,
        )
    )

    portfolio_live_ops = integrate_portfolio_risk_live_ops(
        portfolio=PortfolioRiskInput(
            total_abs_notional_usd=60,
            net_notional_usd=60,
            total_margin_usd=5,
            open_positions_count=1,
            concentration_status="PASS",
        ),
        live_ops=LiveOpsInput(
            safe_mode_active=True,
            kill_switch_active=True,
            supervisor_status=supervisor.status,
            supervisor_allowed_to_continue=supervisor.allowed_to_continue,
            supervisor_blockers=supervisor.blockers,
            supervisor_warnings=supervisor.warnings,
        ),
    )

    blockers = [
        "kill_switch_expected_block",
        *[f"supervisor:{item}" for item in supervisor.blockers],
        *[f"portfolio_live_ops:{item}" for item in portfolio_live_ops.blockers],
    ]

    final_state = SystemStateMachineState.model_validate(transition.resulting_state)

    snapshot = build_unified_system_state_snapshot(
        runtime_context=runtime,
        system_state=final_state,
        blockers=blockers,
        portfolio_live_ops=portfolio_live_ops.model_dump(mode="json"),
        metadata={
            "scenario": "kill_switch",
            "expected_blocked": True,
        },
    )

    expected_blocked = (
        transition.approved
        and safe_mode.approved
        and kill_switch.approved
        and kill_switch.active_after is True
        and final_state.state == "KILL_SWITCH_ACTIVE"
        and snapshot.healthy is False
    )

    warnings = [
        *safe_mode.warnings,
        *kill_switch.warnings,
        *supervisor.warnings,
        *portfolio_live_ops.warnings,
    ]

    return E2EScenarioReport(
        scenario_name="e2e_kill_switch_scenario",
        scenario_kind="kill_switch",
        status="EXPECTED_BLOCKED" if expected_blocked else "FAIL",
        passed=expected_blocked,
        expected_blocked=True,
        blockers=blockers,
        warnings=warnings,
        recommendations=[
            "Kill switch scenario passed only if execution is blocked.",
            "After a real kill switch, require emergency shutdown runbook and human reset.",
        ],
        runtime_context=runtime.model_dump(mode="json"),
        system_state=final_state.model_dump(mode="json"),
        snapshot=snapshot.model_dump(mode="json"),
        components={
            "state_transition": transition.model_dump(mode="json"),
            "safe_mode": safe_mode.model_dump(mode="json"),
            "kill_switch": kill_switch.model_dump(mode="json"),
            "supervisor": supervisor.model_dump(mode="json"),
            "portfolio_live_ops": portfolio_live_ops.model_dump(mode="json"),
        },
        metadata=metadata or {},
    )