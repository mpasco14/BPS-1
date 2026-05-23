from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from data.learning_feedback_dataset import LearningFeedbackRow, load_learning_feedback_jsonl
from strategy.regime_optimization import build_regime_optimization_report, export_regime_optimization_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run regime optimization.")

    parser.add_argument("--input", default=None)
    parser.add_argument("--demo", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/live")
    parser.add_argument("--name", default="regime_optimization_demo")

    return parser.parse_args()


def demo_rows() -> list[LearningFeedbackRow]:
    rows: list[LearningFeedbackRow] = []

    for index in range(15):
        rows.append(
            LearningFeedbackRow(
                decision_id=f"trend_{index}",
                trade_id=f"trend_trade_{index}",
                final_decision="ENTER",
                regime="TRENDING_UP",
                target=1 if index % 3 != 0 else 0,
                realized_net_pnl_usd=1.0 if index % 3 != 0 else -0.5,
            )
        )

    for index in range(15):
        rows.append(
            LearningFeedbackRow(
                decision_id=f"shock_{index}",
                trade_id=f"shock_trade_{index}",
                final_decision="ENTER",
                regime="NEWS_SHOCK",
                target=0 if index % 4 != 0 else 1,
                realized_net_pnl_usd=-1.0 if index % 4 != 0 else 0.2,
            )
        )

    return rows


def main() -> int:
    args = parse_args()

    if args.demo:
        rows = demo_rows()
    elif args.input:
        rows = load_learning_feedback_jsonl(args.input)
    else:
        rows = load_learning_feedback_jsonl()

    report = build_regime_optimization_report(rows=rows)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_regime_optimization_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Regime optimization exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())