from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spot_micro_live.phase35_controlled_exit import (
    build_controlled_fill_session_report,
    build_fee_spread_pnl_reconciliation,
    build_manual_automated_exit_policy,
    build_micro_position_accounting,
    export_json,
    load_phase35_config,
    run_controlled_fill_exit_plan,
    run_kill_switch_residual_inventory,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Phase 35 Spot BRL controlled fill and exit gates."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=[
        "plan",
        "accounting",
        "policy",
        "pnl",
        "kill-switch",
        "report",
],
    )
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--name", default=None)

    args = parser.parse_args()

    config = load_phase35_config()

    if args.mode == "plan":
        report = run_controlled_fill_exit_plan(config)
        name = args.name or "controlled_fill_exit_plan"

    elif args.mode == "accounting":
        report = build_micro_position_accounting(config)
        name = args.name or "micro_position_accounting"

    elif args.mode == "policy":
        report = build_manual_automated_exit_policy(config)
        name = args.name or "manual_automated_exit_policy"

    elif args.mode == "pnl":
        report = build_fee_spread_pnl_reconciliation(config)
        name = args.name or "fee_spread_pnl_reconciliation"

    elif args.mode == "kill-switch":
        report = run_kill_switch_residual_inventory(config)
        name = args.name or "kill_switch_residual_inventory"

    elif args.mode == "report":
        report = build_controlled_fill_session_report(config)
        name = args.name or "controlled_fill_session_report"
    else:
        raise ValueError(f"Unsupported mode: {args.mode}")

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        output_path = export_json(report, output_dir=config.output_dir, name=name)
        print(f"Report exported to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())