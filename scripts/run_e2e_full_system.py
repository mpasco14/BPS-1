from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from e2e.e2e_failure_scenario import run_e2e_failure_scenario
from e2e.e2e_full_system_report import run_all_e2e_scenarios
from e2e.e2e_kill_switch_scenario import run_e2e_kill_switch_scenario
from e2e.e2e_models import export_e2e_scenario_report
from e2e.e2e_paper_trading import run_e2e_paper_trading_scenario
from e2e.e2e_testnet_dry_run import run_e2e_testnet_dry_run_scenario


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run E2E system scenarios.")

    parser.add_argument(
        "--scenario",
        choices=["all", "paper", "testnet", "failure", "kill_switch"],
        default="all",
    )
    parser.add_argument("--session-name", default="e2e_full_system")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/e2e")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.scenario == "all":
        report = run_all_e2e_scenarios(
            session_name=args.session_name,
            export=args.export,
            output_dir=args.output_dir,
        )

        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

        return 0 if report.passed else 1

    scenario_map = {
        "paper": run_e2e_paper_trading_scenario,
        "testnet": run_e2e_testnet_dry_run_scenario,
        "failure": run_e2e_failure_scenario,
        "kill_switch": run_e2e_kill_switch_scenario,
    }

    scenario = scenario_map[args.scenario](session_name=f"{args.session_name}_{args.scenario}")

    print(json.dumps(scenario.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_e2e_scenario_report(
            scenario,
            output_dir=args.output_dir,
            name=scenario.scenario_name,
        )
        print(f"E2E scenario exported: {path}", flush=True)

    return 0 if scenario.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())