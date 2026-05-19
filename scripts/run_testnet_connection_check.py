from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from execution.binance_testnet_client import evaluate_binance_testnet_readiness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Binance Futures testnet readiness check."
    )
    return parser.parse_args()


def main() -> int:
    parse_args()

    report = evaluate_binance_testnet_readiness()

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())