from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from execution.binance_testnet_orders import (
    BinanceTestnetOrderRequest,
    BinanceTestnetOrdersClient,
    export_order_lifecycle_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Binance Futures testnet order lifecycle.")

    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--quantity", default="0.001")
    parser.add_argument("--price", default="10000")
    parser.add_argument("--client-order-id", default=None)

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--test-order", action="store_true")
    parser.add_argument("--cancel-after-create", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/testnet")
    parser.add_argument("--name", default="order_lifecycle_latest")

    return parser.parse_args()


def resolve_dry_run(args: argparse.Namespace) -> bool:
    if args.execute:
        return False

    if args.dry_run:
        return True

    return True


def main() -> int:
    args = parse_args()

    client = BinanceTestnetOrdersClient()

    request = BinanceTestnetOrderRequest(
        symbol=args.symbol,
        side=args.side,
        quantity=args.quantity,
        price=args.price,
        newClientOrderId=args.client_order_id,
    )

    create_result = client.create_order(
        request,
        dry_run=resolve_dry_run(args),
        test_order=args.test_order,
    )

    output = {
        "source": "testnet_order_lifecycle_runner",
        "create": create_result.model_dump(mode="json"),
        "cancel": None,
    }

    if args.cancel_after_create and create_result.status in {"SUBMITTED", "DRY_RUN"}:
        cancel_result = client.cancel_order(
            symbol=args.symbol,
            order_id=create_result.order_id,
            client_order_id=create_result.client_order_id,
            dry_run=resolve_dry_run(args),
        )
        output["cancel"] = cancel_result.model_dump(mode="json")

    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.export:
        path = export_order_lifecycle_result(
            create_result,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Lifecycle result exported: {path}")

    return 0 if create_result.status != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())