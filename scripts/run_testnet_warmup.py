"""
Run testnet warm-up evaluation.

Exemplos:

    python scripts/run_testnet_warmup.py

Com overrides:

    python scripts/run_testnet_warmup.py --days 14 --trades 50 --fill-rate 0.75 --ops-passed --runbook-passed

Exportando:

    python scripts/run_testnet_warmup.py --days 14 --trades 50 --fill-rate 0.75 --ops-passed --runbook-passed --export --name warmup_demo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.testnet_warmup import (
    TestnetWarmupInputs,
    build_testnet_warmup_report,
    export_testnet_warmup_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BTC Binance Futures testnet warm-up check."
    )

    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--trades", type=int, default=None)
    parser.add_argument("--fill-rate", type=float, default=None)
    parser.add_argument("--slippage-error-pct", type=float, default=None)
    parser.add_argument("--critical-alerts", type=int, default=None)
    parser.add_argument("--warning-alerts", type=int, default=None)

    parser.add_argument("--ops-passed", action="store_true")
    parser.add_argument("--runbook-passed", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", type=str, default="artifacts/ops")
    parser.add_argument("--name", type=str, default="testnet_warmup_latest")

    return parser.parse_args()


def maybe_build_inputs_from_args(args: argparse.Namespace) -> TestnetWarmupInputs | None:
    has_override = any(
        value is not None
        for value in [
            args.days,
            args.trades,
            args.fill_rate,
            args.slippage_error_pct,
            args.critical_alerts,
            args.warning_alerts,
        ]
    ) or args.ops_passed or args.runbook_passed

    if not has_override:
        return None

    return TestnetWarmupInputs(
        days_completed=args.days or 0,
        trades_count=args.trades or 0,
        fill_rate=args.fill_rate,
        average_slippage_error_pct=args.slippage_error_pct,
        critical_alerts=args.critical_alerts or 0,
        warning_alerts=args.warning_alerts or 0,
        ops_check_passed=True if args.ops_passed else None,
        runbook_passed=True if args.runbook_passed else None,
    )


def main() -> int:
    args = parse_args()

    inputs = maybe_build_inputs_from_args(args)

    report = build_testnet_warmup_report(
        inputs=inputs,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_testnet_warmup_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )

        print(f"Testnet warm-up report exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())