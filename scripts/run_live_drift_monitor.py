from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from data.learning_feedback_dataset import LearningFeedbackRow, load_learning_feedback_jsonl
from models.live_drift_monitor import build_live_drift_report, export_live_drift_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live model drift monitor.")

    parser.add_argument("--input", default=None)
    parser.add_argument("--demo", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/live")
    parser.add_argument("--name", default="live_drift_demo")

    return parser.parse_args()


def demo_rows() -> list[LearningFeedbackRow]:
    rows: list[LearningFeedbackRow] = []

    for index in range(30):
        target = 1 if index % 3 != 0 else 0

        rows.append(
            LearningFeedbackRow(
                decision_id=f"drift_demo_{index}",
                trade_id=f"trade_{index}",
                final_decision="ENTER",
                model_probability=0.70 if target == 1 else 0.45,
                model_confidence=0.70 if target == 1 else 0.45,
                target=target,
                is_win=bool(target),
                ood_detected=False,
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

    report = build_live_drift_report(rows=rows)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_live_drift_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Live drift report exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())