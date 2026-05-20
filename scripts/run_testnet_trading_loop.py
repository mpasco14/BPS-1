from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from execution.testnet_trading_loop import (
    ControlledTestnetTradeRequest,
    export_controlled_testnet_trade_result,
    run_controlled_testnet_trade,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run controlled Binance Futures testnet trading loop.")

    parser.add_argument("--session-name", default="testnet_controlled_loop")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--quantity", type=float, default=0.001)
    parser.add_argument("--price", type=float, default=10000)
    parser.add_argument("--notional-usd", type=float, default=10)

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cancel-after-create", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/testnet")
    parser.add_argument("--name", default="controlled_testnet_trade_latest")

    return parser.parse_args()


def resolve_dry_run(args: argparse.Namespace) -> bool:
    if args.execute:
        return False

    if args.dry_run:
        return True

    return True


def main() -> int:
    args = parse_args()

    request = ControlledTestnetTradeRequest(
        session_name=args.session_name,
        symbol=args.symbol,
        timeframe=args.timeframe,
        side=args.side,
        quantity=args.quantity,
        price=args.price,
        notional_usd=args.notional_usd,
        dry_run=resolve_dry_run(args),
        cancel_after_create=args.cancel_after_create,
    )

    result = run_controlled_testnet_trade(
        request=request,
    )

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_controlled_testnet_trade_result(
            result,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Controlled testnet trade exported: {path}")

    return 0 if result.status not in {"FAILED", "BLOCKED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())