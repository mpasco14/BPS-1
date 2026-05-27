from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from observability.grafana_dashboard import build_grafana_dashboard_config, export_grafana_dashboard_config
from observability.metrics_registry import load_metrics_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Grafana dashboard config.")

    parser.add_argument("--input", default=None)
    parser.add_argument("--path", default="artifacts/observability/grafana_dashboard_demo.json")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    snapshot = load_metrics_snapshot(args.input) if args.input else None
    dashboard = build_grafana_dashboard_config(snapshot=snapshot)

    print(json.dumps(dashboard, ensure_ascii=False, indent=2))

    path = export_grafana_dashboard_config(dashboard, path=args.path)
    print(f"Grafana dashboard exported: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())