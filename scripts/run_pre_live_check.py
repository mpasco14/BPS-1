"""
Run operational runbook / pre-live / pre-testnet check.

Exemplos:

    python scripts/run_pre_live_check.py --stage testnet
    python scripts/run_pre_live_check.py --stage live
    python scripts/run_pre_live_check.py --stage testnet --export --name pre_testnet_demo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.runbook import RunbookInputs, build_runbook_report, export_runbook_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BTC Binance Futures operational runbook check."
    )

    parser.add_argument(
        "--stage",
        choices=["paper", "testnet", "live"],
        default=None,
    )
    parser.add_argument("--paper-days", type=int, default=None)
    parser.add_argument("--testnet-days", type=int, default=None)
    parser.add_argument("--paper-trades", type=int, default=None)
    parser.add_argument("--testnet-trades", type=int, default=None)
    parser.add_argument("--paper-fill-rate", type=float, default=None)
    parser.add_argument("--testnet-fill-rate", type=float, default=None)
    parser.add_argument("--legal-review-approved", action="store_true")
    parser.add_argument("--testnet-completed", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", type=str, default="artifacts/ops")
    parser.add_argument("--name", type=str, default="runbook_latest")

    return parser.parse_args()


def maybe_override_inputs(args: argparse.Namespace) -> RunbookInputs | None:
    has_override = any(
        value is not None
        for value in [
            args.paper_days,
            args.testnet_days,
            args.paper_trades,
            args.testnet_trades,
            args.paper_fill_rate,
            args.testnet_fill_rate,
        ]
    ) or args.legal_review_approved or args.testnet_completed

    if not has_override:
        return None

    return RunbookInputs(
        paper_days_completed=args.paper_days or 0,
        testnet_days_completed=args.testnet_days or 0,
        paper_trades_count=args.paper_trades or 0,
        testnet_trades_count=args.testnet_trades or 0,
        paper_fill_rate=args.paper_fill_rate,
        testnet_fill_rate=args.testnet_fill_rate,
        legal_review_approved=args.legal_review_approved,
        testnet_completed=args.testnet_completed,
    )


def main() -> int:
    args = parse_args()

    inputs = maybe_override_inputs(args)

    report = build_runbook_report(
        stage=args.stage,
        inputs=inputs,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_runbook_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )

        print(f"Runbook report exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())