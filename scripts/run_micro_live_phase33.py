from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from micro_live.phase33 import (
    build_session_report,
    export_json,
    load_config,
    run_dry_run_signal,
    run_kill_switch,
    run_readonly_check,
    run_small_order,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 33 Micro-Live controlled gates.")
    parser.add_argument(
        "--mode",
        choices=["readonly", "dry-run", "small-order", "kill-switch", "session-report"],
        required=True,
    )
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--name", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()

    if args.mode == "readonly":
        report = run_readonly_check(config)
        name = args.name or "first_micro_live_readonly"

    elif args.mode == "dry-run":
        report = run_dry_run_signal(config)
        name = args.name or "first_micro_live_dry_run_signal"

    elif args.mode == "small-order":
        report = run_small_order(config)
        name = args.name or "first_micro_live_small_order"

    elif args.mode == "kill-switch":
        report = run_kill_switch(config)
        name = args.name or "live_stop_kill_switch_validation"

    else:
        report = build_session_report()
        name = args.name or "micro_live_session_report"

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_json(report, output_dir=config.output_dir, name=name)
        print(f"Report exported to: {path}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())