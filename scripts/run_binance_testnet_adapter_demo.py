from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from binance_testnet_adapter.account_snapshot import (
    export_binance_testnet_account_snapshot,
    fetch_binance_testnet_account_snapshot,
)
from binance_testnet_adapter.api_error import classify_binance_api_error, export_binance_api_error_classification
from binance_testnet_adapter.order_cancel import (
    BinanceTestnetCancelOrderRequest,
    cancel_binance_testnet_order,
    export_binance_testnet_cancel_order_report,
    query_binance_testnet_open_order,
)
from binance_testnet_adapter.order_submit import (
    BinanceTestnetOrderSubmitRequest,
    export_binance_testnet_order_submit_report,
    submit_binance_testnet_order,
)
from binance_testnet_adapter.position_reconciliation import (
    export_binance_testnet_position_reconciliation_report,
    reconcile_binance_testnet_position,
)
from testnet_readiness.testnet_portfolio_reconciliation import build_flat_position


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Binance testnet adapter demo.")

    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/binance_testnet_adapter")
    parser.add_argument("--name", default="binance_testnet_adapter_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    account = fetch_binance_testnet_account_snapshot(symbol=args.symbol)

    order = submit_binance_testnet_order(
        request=BinanceTestnetOrderSubmitRequest(
            symbol=args.symbol,
            side="BUY",
            order_type="LIMIT",
            quantity=0.001,
            price=60000,
            dry_run=True,
            validate_on_exchange=False,
        )
    )

    query = query_binance_testnet_open_order(
        request=BinanceTestnetCancelOrderRequest(
            symbol=args.symbol,
            orig_client_order_id="simulated_order",
        )
    )

    cancel = cancel_binance_testnet_order(
        request=BinanceTestnetCancelOrderRequest(
            symbol=args.symbol,
            orig_client_order_id="simulated_order",
        )
    )

    position_recon = reconcile_binance_testnet_position(
        local_position=build_flat_position(args.symbol),
        account_snapshot=account,
        symbol=args.symbol,
    )

    error_demo = classify_binance_api_error(
        http_status=429,
        error_code=-1003,
        message="Too many requests.",
    )

    payload = {
        "account": account.model_dump(mode="json"),
        "order": order.model_dump(mode="json"),
        "query": query.model_dump(mode="json"),
        "cancel": cancel.model_dump(mode="json"),
        "position_reconciliation": position_recon.model_dump(mode="json"),
        "error_demo": error_demo.model_dump(mode="json"),
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)

        export_binance_testnet_account_snapshot(
            account,
            output_dir=output_dir,
            name=f"{args.name}_account_snapshot",
        )
        export_binance_testnet_order_submit_report(
            order,
            output_dir=output_dir,
            name=f"{args.name}_order_submit",
        )
        export_binance_testnet_cancel_order_report(
            cancel,
            output_dir=output_dir,
            name=f"{args.name}_cancel_order",
        )
        export_binance_testnet_position_reconciliation_report(
            position_recon,
            output_dir=output_dir,
            name=f"{args.name}_position_reconciliation",
        )
        export_binance_api_error_classification(
            error_demo,
            output_dir=output_dir,
            name=f"{args.name}_api_error_classification",
        )

        print(f"Binance testnet adapter artifacts exported to: {output_dir}", flush=True)

    return 0 if account.passed and order.passed and position_recon.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())