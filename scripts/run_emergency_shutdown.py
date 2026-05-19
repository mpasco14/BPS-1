"""
Run emergency shutdown / safe mode.

Uso seguro, sem cancelar ordens reais:

    python scripts/run_emergency_shutdown.py --dry-run

Com export:

    python scripts/run_emergency_shutdown.py --dry-run --export --name shutdown_demo

Com arquivo de ordens abertas:

    python scripts/run_emergency_shutdown.py --dry-run --orders-json artifacts/open_orders.json

Formato de orders-json:
[
  {
    "symbol": "BTCUSDT",
    "client_order_id": "client-1",
    "order_id": 123,
    "side": "BUY",
    "price": 60000,
    "quantity": 0.01,
    "status": "NEW",
    "timeframe": "5m"
  }
]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.emergency_shutdown import (
    clear_safe_mode_state,
    execute_emergency_shutdown,
    export_emergency_shutdown_report,
    load_emergency_shutdown_config,
    load_safe_mode_state,
)


def load_orders_json(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []

    input_path = Path(path)

    if not input_path.exists():
        raise FileNotFoundError(f"orders file not found: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))

    if not isinstance(payload, list):
        raise ValueError("orders-json precisa ser uma lista.")

    return [dict(item) for item in payload]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BTC Binance Futures emergency shutdown."
    )

    parser.add_argument("--reason", type=str, default=None)
    parser.add_argument("--orders-json", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", type=str, default="artifacts/ops")
    parser.add_argument("--name", type=str, default="emergency_shutdown_latest")
    parser.add_argument("--show-state", action="store_true")
    parser.add_argument("--clear-state", action="store_true")

    return parser.parse_args()


def resolve_dry_run(args: argparse.Namespace) -> bool:
    if args.execute:
        return False

    if args.dry_run:
        return True

    config = load_emergency_shutdown_config()

    return config.dry_run


def main() -> int:
    args = parse_args()
    config = load_emergency_shutdown_config()

    if args.show_state:
        state = load_safe_mode_state(config.state_file)
        print(json.dumps(state.model_dump(mode="json") if state else None, ensure_ascii=False, indent=2))
        return 0

    if args.clear_state:
        removed = clear_safe_mode_state(config.state_file)
        print(json.dumps({"removed": removed, "state_file": str(config.state_file)}, ensure_ascii=False, indent=2))
        return 0

    orders = load_orders_json(args.orders_json)

    report = execute_emergency_shutdown(
        open_orders=orders,
        reason=args.reason,
        config=config,
        dry_run=resolve_dry_run(args),
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_emergency_shutdown_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )

        print(f"Emergency shutdown report exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())