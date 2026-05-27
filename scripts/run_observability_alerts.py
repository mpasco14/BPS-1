from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from observability.alert_rules import evaluate_alert_rules, export_alert_evaluation_report
from observability.metrics_registry import build_core_metrics_snapshot, load_metrics_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate observability alert rules.")

    parser.add_argument("--input", default=None)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/observability")
    parser.add_argument("--name", default="alert_evaluation_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    snapshot = load_metrics_snapshot(args.input) if args.input else None

    if snapshot is None:
        snapshot = build_core_metrics_snapshot(
            live_performance={"fill_rate": 0.75, "rejection_rate": 0.02},
            live_risk_audit={"critical_findings_count": 0},
            drift_report={"ood_rate": 0.05},
            production_guard={"blocking_fail_count": 0},
        )

    report = evaluate_alert_rules(snapshot=snapshot)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_alert_evaluation_report(report, output_dir=args.output_dir, name=args.name)
        print(f"Alert evaluation exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())