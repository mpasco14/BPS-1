from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.decision_journal import (
    DecisionEvidence,
    append_decision_journal_entry,
    build_decision_journal_entry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run decision journal demo.")

    parser.add_argument("--append", action="store_true")
    parser.add_argument("--path", default=None)

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    entry = build_decision_journal_entry(
        decision_id="demo_decision_001",
        symbol="BTCUSDT",
        side="BUY",
        decision_source="system",
        evidence=DecisionEvidence(
            signal_id="signal_demo_001",
            model_version="demo_model",
            model_probability=0.72,
            model_confidence=0.72,
            expected_value_usd=0.5,
            technical_score=0.8,
            onchain_score=0.1,
            sentiment_score=0.05,
            data_quality_passed=True,
            risk_approved=True,
            execution_allowed=True,
            spread_pct=0.0002,
            liquidity_usd=100000,
            timeframe="5m",
        ),
    )

    print(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.append:
        path = append_decision_journal_entry(entry, path=args.path)
        print(f"Decision journal entry appended: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())