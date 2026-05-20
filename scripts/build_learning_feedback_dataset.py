from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from data.learning_feedback_dataset import (
    build_learning_feedback_row,
    export_learning_feedback_jsonl,
)
from ops.decision_journal import DecisionEvidence, build_decision_journal_entry
from ops.outcome_attribution import TradeOutcomeInput, build_outcome_attribution_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build learning feedback dataset demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--path", default="artifacts/learning/learning_feedback_dataset_demo.jsonl")

    return parser.parse_args()


def build_demo_row():
    decision = build_decision_journal_entry(
        decision_id="demo_decision_feedback_001",
        symbol="BTCUSDT",
        side="BUY",
        evidence=DecisionEvidence(
            signal_id="signal_demo",
            model_version="demo_model",
            model_probability=0.72,
            model_confidence=0.72,
            expected_value_usd=0.50,
            technical_score=0.8,
            onchain_score=0.1,
            sentiment_score=0.2,
            microstructure_score=0.3,
            data_quality_passed=True,
            risk_approved=True,
            execution_allowed=True,
            spread_pct=0.0002,
            liquidity_usd=100000,
            regime="TRENDING_UP",
            timeframe="5m",
        ),
    )

    outcome = build_outcome_attribution_report(
        TradeOutcomeInput(
            trade_id="demo_trade_feedback_001",
            side="BUY",
            predicted_probability=0.72,
            expected_value_usd=0.50,
            realized_pnl_usd=1.20,
            fees_usd=0.10,
            expected_slippage_pct=0.0005,
            realized_slippage_pct=0.0004,
            latency_ms=200,
            regime="TRENDING_UP",
        )
    )

    return build_learning_feedback_row(decision=decision, outcome=outcome)


def main() -> int:
    args = parse_args()
    row = build_demo_row()

    print(json.dumps(row.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_learning_feedback_jsonl([row], path=args.path)
        print(f"Learning feedback dataset exported: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())