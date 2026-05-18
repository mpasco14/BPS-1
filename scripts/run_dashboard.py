"""
Run local dashboard.

Uso:

    python scripts/run_dashboard.py

Ou:

    python scripts/run_dashboard.py --host 127.0.0.1 --port 8050
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from dashboard.config import load_dashboard_config
from dashboard.api import run_dashboard_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BTC Binance Futures local dashboard."
    )

    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--refresh-seconds", type=int, default=None)
    parser.add_argument("--theme", type=str, default=None)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_dashboard_config()

    if args.host is not None:
        config.host = args.host

    if args.port is not None:
        config.port = args.port

    if args.refresh_seconds is not None:
        config.refresh_seconds = args.refresh_seconds

    if args.theme is not None:
        config.theme = args.theme

    run_dashboard_server(config)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())