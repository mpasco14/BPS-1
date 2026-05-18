"""
Run observability metrics server.

Uso:

    python scripts/run_metrics_server.py

Depois acesse:

    http://127.0.0.1:8001/metrics
    http://127.0.0.1:8001/health
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from observability.metrics import run_observability_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BTC Binance Futures observability server."
    )

    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    run_observability_server(
        host=args.host,
        port=args.port,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())