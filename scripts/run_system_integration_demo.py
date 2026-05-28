from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from system_integration.execution_contract import RiskApprovalDecision
from system_integration.portfolio_live_ops_integration import LiveOpsInput, PortfolioRiskInput, integrate_portfolio_risk_live_ops
from system_integration.runtime_context import build_integrated_runtime_context, export_runtime_context
from system_integration.sentiment_journal_integration import SentimentNoTradeInput, integrate_sentiment_no_trade_journal
from system_integration.signal_risk_execution_adapter import SignalDecision, adapt_signal_to_risk_execution
from system_integration.system_state_machine import (
    StateTransitionRequest,
    SystemStateMachineState,
    evaluate_state_transition,
    export_state_transition_decision,
)
from system_integration.system_state_snapshot import (
    build_unified_system_state_snapshot,
    export_unified_system_state_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run system integration demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/system_integration")
    parser.add_argument("--name", default="system_integration_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    runtime = build_integrated_runtime_context(
        environment="development",
        execution_mode="paper",
        session_name=args.name,
        operator="Paulo",
        feature_flags={"sentiment_intelligence": True},
    )

    transition = evaluate_state_transition(
        current=SystemStateMachineState(state="CONFIG_VALIDATION"),
        request=StateTransitionRequest(
            action="MARK_PAPER_READY",
            requested_by="demo",
            reason="Demo config validated.",
            config_valid=True,
        ),
    )

    sentiment = integrate_sentiment_no_trade_journal(
        sentiment=SentimentNoTradeInput(
            asset="BTCUSDT",
            timeframe="5m",
            sentiment_index=62,
            fear_greed_value=62,
            confidence=0.75,
            regime="greed",
        )
    )

    pipeline = adapt_signal_to_risk_execution(
        signal=SignalDecision(
            symbol="BTCUSDT",
            timeframe="5m",
            direction="BUY",
            probability=0.66,
            confidence=0.72,
            edge=0.015,
            suggested_quantity=0.001,
            suggested_price=60000,
            suggested_notional_usd=60,
            suggested_margin_usd=5,
            suggested_leverage=12,
        ),
        risk_decision=RiskApprovalDecision(approved=True, risk_score=0.25),
        execution_mode="paper",
    )

    portfolio_live_ops = integrate_portfolio_risk_live_ops(
        portfolio=PortfolioRiskInput(
            total_abs_notional_usd=60,
            net_notional_usd=60,
            total_margin_usd=5,
            open_positions_count=1,
            realized_net_pnl_usd=0,
            concentration_status="PASS",
        ),
        live_ops=LiveOpsInput(
            safe_mode_active=False,
            kill_switch_active=False,
            supervisor_status="RUNNING",
            supervisor_allowed_to_continue=True,
        ),
    )

    snapshot = build_unified_system_state_snapshot(
        runtime_context=runtime,
        system_state=SystemStateMachineState.model_validate(transition.resulting_state),
        blockers=[],
        signal_pipeline=pipeline.model_dump(mode="json"),
        sentiment_journal=sentiment.model_dump(mode="json"),
        portfolio_live_ops=portfolio_live_ops.model_dump(mode="json"),
        execution_contract=pipeline.execution_contract,
        metadata={"demo": True},
    )

    payload = {
        "runtime": runtime.model_dump(mode="json"),
        "transition": transition.model_dump(mode="json"),
        "sentiment": sentiment.model_dump(mode="json"),
        "pipeline": pipeline.model_dump(mode="json"),
        "portfolio_live_ops": portfolio_live_ops.model_dump(mode="json"),
        "snapshot": snapshot.model_dump(mode="json"),
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)
        export_runtime_context(runtime, output_dir=output_dir, name=f"{args.name}_runtime")
        export_state_transition_decision(transition, output_dir=output_dir, name=f"{args.name}_state_transition")
        export_unified_system_state_snapshot(snapshot, path=output_dir / f"{args.name}_snapshot.json")
        print(f"System integration demo exported to: {output_dir}", flush=True)

    return 0 if snapshot.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())