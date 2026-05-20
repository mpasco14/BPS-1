from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from data.learning_feedback_dataset import LearningFeedbackRow, load_learning_feedback_jsonl
from ops.threshold_review import build_threshold_review_report, export_threshold_review_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run adaptive threshold review.")

    parser.add_argument("--input", default=None)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/governance")
    parser.add_argument("--name", default="threshold_review_demo")

    return parser.parse_args()


def demo_rows() -> list[LearningFeedbackRow]:
    rows: list[LearningFeedbackRow] = []

    for index in range(25):
        rows.append(
            LearningFeedbackRow(
                decision_id=f"demo_{index}",
                trade_id=f"trade_{index}",
                symbol="BTCUSDT",
                timeframe="5m",
                side="BUY",
                final_decision="ENTER",
                model_confidence=0.70,
                model_probability=0.70,
                expected_value_usd=0.20,
                realized_net_pnl_usd=1.0 if index % 2 == 0 else -0.5,
                is_win=index % 2 == 0,
                target=1 if index % 2 == 0 else 0,
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

    report = build_threshold_review_report(rows=rows)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_threshold_review_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Threshold review exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())