from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from observability.metrics_registry import build_core_metrics_snapshot, load_metrics_snapshot
from observability.prometheus_exporter import export_prometheus_metrics, render_prometheus_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Prometheus metrics.")

    parser.add_argument("--input", default=None)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--path", default="artifacts/observability/prometheus_metrics_demo.prom")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    snapshot = load_metrics_snapshot(args.input) if args.input else None

    if snapshot is None:
        snapshot = build_core_metrics_snapshot(
            live_performance={"fill_rate": 0.75, "rejection_rate": 0.02, "net_pnl_usd": 3.5},
            live_risk_audit={"critical_findings_count": 0},
            drift_report={"ood_rate": 0.05},
            production_guard={"blocking_fail_count": 0},
        )

    text = render_prometheus_text(snapshot)

    print(text)

    if args.export:
        path = export_prometheus_metrics(snapshot, path=args.path)
        print(f"Prometheus metrics exported: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())