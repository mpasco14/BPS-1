from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from testnet_order_lifecycle.cancel_order import export_cancel_order_report
from testnet_order_lifecycle.fill_rejection_capture import export_fill_rejection_capture_report
from testnet_order_lifecycle.lifecycle_models import TestnetOrderLifecycleConfig, load_testnet_order_lifecycle_config
from testnet_order_lifecycle.lifecycle_report import build_real_testnet_lifecycle_report, export_real_testnet_lifecycle_report
from testnet_order_lifecycle.open_order_query import export_open_order_query_report
from testnet_order_lifecycle.small_limit_order_submit import export_small_limit_order_submit_report
from testnet_order_lifecycle.test_order_validation import export_test_order_validation_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real/simulated Binance testnet order lifecycle.")

    parser.add_argument("--symbol", default=None)
    parser.add_argument("--side", choices=["BUY", "SELL"], default=None)
    parser.add_argument("--quantity", type=float, default=None)
    parser.add_argument("--price", type=float, default=None)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--real-testnet", action="store_true")
    parser.add_argument("--allow-submit", action="store_true")
    parser.add_argument("--allow-cancel", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/testnet_order_lifecycle")
    parser.add_argument("--name", default="real_testnet_order_lifecycle")

    return parser.parse_args()


def build_config_from_args(args: argparse.Namespace) -> TestnetOrderLifecycleConfig:
    base = load_testnet_order_lifecycle_config()

    simulate = base.simulate
    if args.simulate:
        simulate = True
    if args.real_testnet:
        simulate = False

    return base.model_copy(
        update={
            "symbol": args.symbol or base.symbol,
            "side": args.side or base.side,
            "quantity": args.quantity if args.quantity is not None else base.quantity,
            "price": args.price if args.price is not None else base.price,
            "simulate": simulate,
            "allow_real_submit": args.allow_submit if args.allow_submit else base.allow_real_submit,
            "allow_real_cancel": args.allow_cancel if args.allow_cancel else base.allow_real_cancel,
        }
    )


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    config = build_config_from_args(args)

    report = build_real_testnet_lifecycle_report(config=config)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)

        if report.test_order:
            export_test_order_validation_report(
                report.test_order,
                output_dir=output_dir,
                name=f"{args.name}_test_order",
            )

        if report.submit:
            export_small_limit_order_submit_report(
                report.submit,
                output_dir=output_dir,
                name=f"{args.name}_submit",
            )

        if report.open_order_query:
            export_open_order_query_report(
                report.open_order_query,
                output_dir=output_dir,
                name=f"{args.name}_open_order_query",
            )

        if report.cancel:
            export_cancel_order_report(
                report.cancel,
                output_dir=output_dir,
                name=f"{args.name}_cancel",
            )

        if report.fill_capture:
            export_fill_rejection_capture_report(
                report.fill_capture,
                output_dir=output_dir,
                name=f"{args.name}_fill_capture",
            )

        export_real_testnet_lifecycle_report(
            report,
            output_dir=output_dir,
            name=f"{args.name}_report",
        )

        print(f"Real testnet order lifecycle artifacts exported to: {output_dir}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())