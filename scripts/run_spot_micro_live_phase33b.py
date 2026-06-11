from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spot_micro_live.phase33b import (
    build_spot_session_report,
    export_json,
    load_config,
    run_spot_brl_filter_validation,
    run_spot_brl_pair_discovery,
    run_spot_credential_permission_check,
    run_spot_dry_run_execution_contract,
    run_spot_kill_switch,
    run_spot_readonly_snapshot,
    run_spot_reconciliation,
    run_spot_small_limit_order,
    run_venue_availability_check,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 33B Binance Spot micro-live gates.")
    parser.add_argument(
        "--mode",
        choices=[
            "venue",
            "credential",
            "pair-discovery",
            "filters",
            "readonly",
            "dry-run",
            "small-order",
            "reconciliation",
            "kill-switch",
            "session-report",
        ],
        required=True,
    )
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--name", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()

    if args.mode == "venue":
        report = run_venue_availability_check(config)
        name = args.name or "spot_venue_availability"
    elif args.mode == "credential":
        report = run_spot_credential_permission_check(config)
        name = args.name or "spot_credential_permission"
    elif args.mode == "pair-discovery":
        report = run_spot_brl_pair_discovery(config)
        name = args.name or "spot_brl_pair_discovery"
    elif args.mode == "filters":
        report = run_spot_brl_filter_validation(config)
        name = args.name or "spot_brl_filter_validation"  
    elif args.mode == "readonly":
        report = run_spot_readonly_snapshot(config)
        name = args.name or "spot_micro_live_readonly"
    elif args.mode == "dry-run":
        report = run_spot_dry_run_execution_contract(config)
        name = args.name or "spot_micro_live_dry_run_signal"
    elif args.mode == "small-order":
        report = run_spot_small_limit_order(config)
        name = args.name or "spot_micro_live_small_order"
    elif args.mode == "reconciliation":
        report = run_spot_reconciliation(config)
        name = args.name or "spot_micro_live_reconciliation"
    elif args.mode == "kill-switch":
        report = run_spot_kill_switch(config)
        name = args.name or "spot_micro_live_kill_switch"
    else:
        report = build_spot_session_report(config)
        name = args.name or "spot_micro_live_session_report"

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_json(report, output_dir=config.output_dir, name=name)
        print(f"Report exported to: {path}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
