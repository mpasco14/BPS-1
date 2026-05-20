from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.testnet_continuous import (
    build_testnet_continuous_report,
    export_testnet_continuous_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run testnet continuous report.")

    parser.add_argument("--input-dir", default="artifacts/testnet")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/testnet")
    parser.add_argument("--name", default="testnet_continuous_latest")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    report = build_testnet_continuous_report()

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_testnet_continuous_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Testnet continuous report exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())