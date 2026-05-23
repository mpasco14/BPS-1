from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from infra.dependency_health import build_dependency_health_report, export_dependency_health_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run infrastructure dependency health check.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/infra")
    parser.add_argument("--name", default="dependency_health_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_dependency_health_report()

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_dependency_health_report(report, output_dir=args.output_dir, name=args.name)
        print(f"Dependency health exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())