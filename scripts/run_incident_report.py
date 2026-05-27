from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from observability.alert_rules import evaluate_alert_rules
from observability.incident_report import export_incident_report, generate_incident_report
from observability.metrics_registry import build_core_metrics_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate incident report demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/observability")
    parser.add_argument("--name", default="incident_report_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    snapshot = build_core_metrics_snapshot(
        live_performance={"fill_rate": 0.40, "rejection_rate": 0.20},
        live_risk_audit={"critical_findings_count": 1},
        drift_report={"ood_rate": 0.30},
        production_guard={"blocking_fail_count": 1},
    )

    alerts = evaluate_alert_rules(snapshot=snapshot)
    incident = generate_incident_report(alert_report=alerts, metrics_snapshot=snapshot)

    print(json.dumps(incident.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_incident_report(incident, output_dir=args.output_dir, name=args.name)
        print(f"Incident report exported: {path}")

    return 0 if not incident.active else 1


if __name__ == "__main__":
    raise SystemExit(main())