from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from infra.runtime_config_validator import export_runtime_config_validation_report, validate_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run runtime config validation.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/infra")
    parser.add_argument("--name", default="runtime_config_validation_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_runtime_config()

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_runtime_config_validation_report(report, output_dir=args.output_dir, name=args.name)
        print(f"Runtime config validation exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())