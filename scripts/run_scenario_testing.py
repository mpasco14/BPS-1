from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scenario_testing.chop_sideways_scenario import run_chop_sideways_scenario
from scenario_testing.news_sentiment_shock_scenario import run_news_sentiment_shock_scenario
from scenario_testing.scenario_models import export_scenario_report
from scenario_testing.scenario_testing_report import run_all_scenario_tests
from scenario_testing.trend_regime_scenario import run_trend_regime_scenario
from scenario_testing.volatility_shock_scenario import run_volatility_shock_scenario


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run historical replay and scenario testing.")

    parser.add_argument(
        "--scenario",
        choices=["all", "volatility", "trend_up", "trend_down", "chop", "news"],
        default="all",
    )
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/scenario_testing")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.scenario == "all":
        report = run_all_scenario_tests(
            export=args.export,
            output_dir=args.output_dir,
        )

        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

        return 0 if report.passed else 1

    scenario_map = {
        "volatility": run_volatility_shock_scenario,
        "trend_up": lambda: run_trend_regime_scenario(trend_direction="uptrend"),
        "trend_down": lambda: run_trend_regime_scenario(trend_direction="downtrend"),
        "chop": run_chop_sideways_scenario,
        "news": run_news_sentiment_shock_scenario,
    }

    report = scenario_map[args.scenario]()

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_scenario_report(
            report,
            output_dir=args.output_dir,
            name=report.scenario_name,
        )
        print(f"Scenario report exported: {path}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())