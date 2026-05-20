from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from strategy.no_trade_engine import NoTradeInput, evaluate_no_trade, export_no_trade_decision


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run no-trade engine demo.")

    parser.add_argument("--blocked-demo", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/governance")
    parser.add_argument("--name", default="no_trade_demo")

    return parser.parse_args()


def build_demo_input(blocked: bool) -> NoTradeInput:
    if blocked:
        return NoTradeInput(
            model_confidence=0.50,
            expected_value_usd=-0.10,
            spread_pct=0.005,
            liquidity_usd=10000,
            regime="HIGH_VOLATILITY",
            risk_state_status="OK",
        )

    return NoTradeInput(
        model_confidence=0.72,
        expected_value_usd=0.50,
        spread_pct=0.0002,
        liquidity_usd=100000,
        regime="TRENDING_UP",
        risk_state_status="OK",
    )


def main() -> int:
    args = parse_args()

    decision = evaluate_no_trade(input_data=build_demo_input(args.blocked_demo))

    print(json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_no_trade_decision(
            decision,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"No-trade decision exported: {path}")

    return 0 if decision.should_trade else 1


if __name__ == "__main__":
    raise SystemExit(main())