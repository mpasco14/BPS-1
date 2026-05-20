from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.strategy_health import (
    StrategyHealthInput,
    build_strategy_health_report,
    export_strategy_health_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strategy health demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/governance")
    parser.add_argument("--name", default="strategy_health_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    report = build_strategy_health_report(
        input_data=StrategyHealthInput(
            trades_count=50,
            net_pnl_usd=10,
            max_drawdown_pct=0.04,
            profit_factor=1.25,
            win_rate=0.55,
            fill_rate=0.75,
            rejection_rate=0.02,
            expected_calibration_error=0.08,
            ood_rate=0.05,
            discipline_score=0.95,
            risk_state_status="OK",
        )
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_strategy_health_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Strategy health exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())