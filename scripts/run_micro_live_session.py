from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from micro_live_session.dry_run_signal import MicroLiveDryRunSignalInput, export_micro_live_dry_run_signal_report
from micro_live_session.fill_reconciliation_review import export_micro_live_fill_reconciliation_report
from micro_live_session.kill_switch_validation import export_micro_live_kill_switch_validation_report
from micro_live_session.read_only_check import export_first_micro_live_read_only_check_report
from micro_live_session.session_models import MicroLiveSessionConfig, load_micro_live_session_config
from micro_live_session.session_report import build_micro_live_session_report, export_micro_live_session_report
from micro_live_session.small_order_gate import export_micro_live_small_order_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run first supervised micro-live session gate.")

    parser.add_argument("--session-name", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--side", choices=["BUY", "SELL"], default=None)
    parser.add_argument("--quantity", type=float, default=None)
    parser.add_argument("--price", type=float, default=None)
    parser.add_argument("--confidence", type=float, default=0.75)
    parser.add_argument("--edge-pct", type=float, default=0.002)

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-live-order", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/micro_live_session")
    parser.add_argument("--name", default="first_micro_live_session")

    return parser.parse_args()


def build_config_from_args(args: argparse.Namespace) -> MicroLiveSessionConfig:
    base = load_micro_live_session_config()

    dry_run = True if args.dry_run else base.dry_run

    return base.model_copy(
        update={
            "session_name": args.session_name or base.session_name,
            "symbol": args.symbol or base.symbol,
            "side": args.side or base.side,
            "quantity": args.quantity if args.quantity is not None else base.quantity,
            "price": args.price if args.price is not None else base.price,
            "dry_run": dry_run,
            "allow_live_order": args.allow_live_order if args.allow_live_order else base.allow_live_order,
        }
    )


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    config = build_config_from_args(args)

    signal_input = MicroLiveDryRunSignalInput(
        symbol=config.symbol,
        side=config.side,
        confidence=args.confidence,
        edge_pct=args.edge_pct,
        read_only_passed=True,
        strategy_health_passed=True,
        no_trade_engine_passed=True,
    )

    report = build_micro_live_session_report(
        config=config,
        signal_input=signal_input,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)

        if report.read_only_check:
            export_first_micro_live_read_only_check_report(
                report.read_only_check,
                output_dir=output_dir,
                name=f"{args.name}_read_only_check",
            )

        if report.dry_run_signal:
            export_micro_live_dry_run_signal_report(
                report.dry_run_signal,
                output_dir=output_dir,
                name=f"{args.name}_dry_run_signal",
            )

        if report.small_order:
            export_micro_live_small_order_report(
                report.small_order,
                output_dir=output_dir,
                name=f"{args.name}_small_order",
            )

        if report.fill_reconciliation:
            export_micro_live_fill_reconciliation_report(
                report.fill_reconciliation,
                output_dir=output_dir,
                name=f"{args.name}_fill_reconciliation",
            )

        if report.kill_switch:
            export_micro_live_kill_switch_validation_report(
                report.kill_switch,
                output_dir=output_dir,
                name=f"{args.name}_kill_switch",
            )

        export_micro_live_session_report(
            report,
            output_dir=output_dir,
            name=f"{args.name}_report",
        )

        print(f"Micro-live session artifacts exported to: {output_dir}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())