from __future__ import annotations

from typing import Any

from e2e.e2e_models import E2EScenarioReport, load_e2e_config, scenario_status_from_result
from system_integration.execution_contract import RiskApprovalDecision
from system_integration.portfolio_live_ops_integration import (
    LiveOpsInput,
    PortfolioRiskInput,
    integrate_portfolio_risk_live_ops,
)
from system_integration.runtime_context import build_integrated_runtime_context
from system_integration.sentiment_journal_integration import (
    SentimentNoTradeInput,
    integrate_sentiment_no_trade_journal,
)
from system_integration.signal_risk_execution_adapter import (
    SignalDecision,
    adapt_signal_to_risk_execution,
)
from system_integration.system_state_machine import (
    StateTransitionRequest,
    SystemStateMachineState,
    evaluate_state_transition,
)
from system_integration.system_state_snapshot import build_unified_system_state_snapshot


def run_e2e_paper_trading_scenario(
    *,
    session_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> E2EScenarioReport:
    config = load_e2e_config()
    resolved_session = session_name or f"{config.session_name}_paper"

    runtime = build_integrated_runtime_context(
        environment="paper",
        execution_mode="paper",
        session_name=resolved_session,
        operator="e2e",
        feature_flags={
            "sentiment_intelligence": True,
            "adaptive_threshold_review": True,
        },
        metadata={"scenario": "paper_trading"},
    )

    paper_ready = evaluate_state_transition(
        current=SystemStateMachineState(state="CONFIG_VALIDATION"),
        request=StateTransitionRequest(
            action="MARK_PAPER_READY",
            requested_by="e2e",
            reason="E2E paper scenario config validated.",
            config_valid=True,
        ),
    )

    running = evaluate_state_transition(
        current=SystemStateMachineState.model_validate(paper_ready.resulting_state),
        request=StateTransitionRequest(
            action="START_RUNNING",
            requested_by="e2e",
            reason="E2E paper scenario start running.",
            kill_switch_clear=True,
            safe_mode_clear=True,
        ),
    )

    sentiment = integrate_sentiment_no_trade_journal(
        sentiment=SentimentNoTradeInput(
            asset=config.default_symbol,
            timeframe=config.default_timeframe,
            sentiment_index=55,
            fear_greed_value=55,
            confidence=0.75,
            regime="neutral",
        ),
        metadata={"scenario": "paper_trading"},
    )

    pipeline = adapt_signal_to_risk_execution(
        signal=SignalDecision(
            symbol=config.default_symbol,
            timeframe=config.default_timeframe,
            direction="BUY",
            probability=0.67,
            confidence=0.72,
            edge=0.018,
            suggested_quantity=0.001,
            suggested_price=60000,
            suggested_notional_usd=60,
            suggested_margin_usd=5,
            suggested_leverage=12,
            metadata={"scenario": "paper_trading"},
        ),
        risk_decision=RiskApprovalDecision(
            approved=True,
            risk_score=0.25,
            metadata={"scenario": "paper_trading"},
        ),
        execution_mode="paper",
        live_submission_allowed=False,
        human_approval_valid=False,
        production_guard_passed=False,
        safe_mode_active=False,
        kill_switch_active=False,
    )

    portfolio_live_ops = integrate_portfolio_risk_live_ops(
        portfolio=PortfolioRiskInput(
            total_abs_notional_usd=60,
            net_notional_usd=60,
            total_margin_usd=5,
            open_positions_count=1,
            realized_net_pnl_usd=0,
            max_leverage_seen=12,
            concentration_status="PASS",
        ),
        live_ops=LiveOpsInput(
            safe_mode_active=False,
            kill_switch_active=False,
            supervisor_status="RUNNING",
            supervisor_allowed_to_continue=True,
        ),
    )

    blockers: list[str] = []
    warnings: list[str] = []

    if not paper_ready.approved:
        blockers.extend([f"paper_ready:{item}" for item in paper_ready.blockers])

    if not running.approved:
        blockers.extend([f"running:{item}" for item in running.blockers])

    if not sentiment.approved_for_signal:
        blockers.extend([f"sentiment:{item}" for item in sentiment.blockers])

    if not pipeline.approved:
        blockers.extend([f"pipeline:{item}" for item in pipeline.blockers])

    if not portfolio_live_ops.allowed_to_continue:
        blockers.extend([f"portfolio_live_ops:{item}" for item in portfolio_live_ops.blockers])

    warnings.extend([f"sentiment:{item}" for item in sentiment.warnings])
    warnings.extend([f"pipeline:{item}" for item in pipeline.warnings])
    warnings.extend([f"portfolio_live_ops:{item}" for item in portfolio_live_ops.warnings])

    final_state = SystemStateMachineState.model_validate(running.resulting_state)

    snapshot = build_unified_system_state_snapshot(
        runtime_context=runtime,
        system_state=final_state,
        blockers=blockers,
        signal_pipeline=pipeline.model_dump(mode="json"),
        sentiment_journal=sentiment.model_dump(mode="json"),
        portfolio_live_ops=portfolio_live_ops.model_dump(mode="json"),
        execution_contract=pipeline.execution_contract,
        metadata={"scenario": "paper_trading"},
    )

    passed = not blockers and snapshot.healthy

    return E2EScenarioReport(
        scenario_name="e2e_paper_trading_scenario",
        scenario_kind="paper_trading",
        status=scenario_status_from_result(passed=passed, warnings=warnings),
        passed=passed,
        blockers=blockers,
        warnings=warnings,
        recommendations=[
            "Paper scenario approved only for simulated execution.",
            "Use this result as prerequisite for testnet dry-run.",
        ],
        runtime_context=runtime.model_dump(mode="json"),
        system_state=final_state.model_dump(mode="json"),
        snapshot=snapshot.model_dump(mode="json"),
        components={
            "paper_ready_transition": paper_ready.model_dump(mode="json"),
            "running_transition": running.model_dump(mode="json"),
            "sentiment_journal": sentiment.model_dump(mode="json"),
            "signal_pipeline": pipeline.model_dump(mode="json"),
            "portfolio_live_ops": portfolio_live_ops.model_dump(mode="json"),
        },
        metadata=metadata or {},
    )