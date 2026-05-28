from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from testnet_readiness.testnet_acceptance_report import build_testnet_acceptance_report, export_testnet_acceptance_report
from testnet_readiness.testnet_fill_monitoring import build_demo_fill_events, export_testnet_fill_monitor_report, monitor_testnet_fills_and_rejections
from testnet_readiness.testnet_order_lifecycle import build_demo_lifecycle_events, export_testnet_order_lifecycle_report, validate_testnet_order_lifecycle
from testnet_readiness.testnet_portfolio_reconciliation import build_flat_position, export_testnet_portfolio_reconciliation_report, reconcile_testnet_portfolio
from testnet_readiness.testnet_reconciliation_engine import export_testnet_reconciliation_engine_report, run_testnet_reconciliation_engine
from testnet_readiness.testnet_session_plan import build_testnet_session_plan, evaluate_testnet_session_plan, export_testnet_session_plan_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run testnet readiness demo.")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/testnet_readiness")
    parser.add_argument("--name", default="testnet_readiness_demo")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    plan = evaluate_testnet_session_plan(
        plan=build_testnet_session_plan(
            session_name=args.name,
            e2e_passed=True,
            scenario_testing_passed=True,
            kill_switch_test_passed=True,
        )
    )

    lifecycle = validate_testnet_order_lifecycle(events=build_demo_lifecycle_events())
    fill_monitor = monitor_testnet_fills_and_rejections(events=build_demo_fill_events())

    portfolio = reconcile_testnet_portfolio(
        local_position=build_flat_position(),
        exchange_position=build_flat_position(),
    )

    engine = run_testnet_reconciliation_engine(
        lifecycle=lifecycle,
        fill_monitor=fill_monitor,
        portfolio_reconciliation=portfolio,
    )

    acceptance = build_testnet_acceptance_report(
        plan=plan,
        lifecycle=lifecycle,
        fill_monitor=fill_monitor,
        portfolio_reconciliation=portfolio,
        reconciliation_engine=engine,
    )

    print(json.dumps(acceptance.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        export_testnet_session_plan_report(plan, output_dir=output_dir, name=f"{args.name}_session_plan")
        export_testnet_order_lifecycle_report(lifecycle, output_dir=output_dir, name=f"{args.name}_order_lifecycle")
        export_testnet_fill_monitor_report(fill_monitor, output_dir=output_dir, name=f"{args.name}_fill_monitor")
        export_testnet_portfolio_reconciliation_report(portfolio, output_dir=output_dir, name=f"{args.name}_portfolio_reconciliation")
        export_testnet_reconciliation_engine_report(engine, output_dir=output_dir, name=f"{args.name}_reconciliation_engine")
        export_testnet_acceptance_report(acceptance, output_dir=output_dir, name=f"{args.name}_acceptance")

        print(f"Testnet readiness artifacts exported to: {output_dir}", flush=True)

    return 0 if acceptance.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())