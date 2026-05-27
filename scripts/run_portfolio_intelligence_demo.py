from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from portfolio_intelligence.exposure_concentration_guard import (
    evaluate_exposure_concentration,
    export_exposure_concentration_report,
)
from portfolio_intelligence.exposure_ledger import (
    build_exposure_ledger,
    demo_exposure_events,
    export_exposure_ledger_summary,
    summarize_exposure_ledger,
)
from portfolio_intelligence.pnl_attribution import build_pnl_attribution_report, export_pnl_attribution_report
from portfolio_intelligence.portfolio_risk_dashboard import (
    build_portfolio_risk_dashboard,
    export_portfolio_risk_dashboard,
)
from portfolio_intelligence.position_lifecycle import build_position_lifecycle_report, export_position_lifecycle_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run portfolio intelligence demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/portfolio")
    parser.add_argument("--name", default="portfolio_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    events = demo_exposure_events()
    ledger = build_exposure_ledger(events=events)
    summary = summarize_exposure_ledger(ledger=ledger)
    lifecycle = build_position_lifecycle_report(events=events)
    concentration = evaluate_exposure_concentration(summary=summary, lifecycle=lifecycle)
    pnl = build_pnl_attribution_report(events=events)

    dashboard = build_portfolio_risk_dashboard(
        summary=summary,
        lifecycle=lifecycle,
        concentration=concentration,
        pnl_attribution=pnl,
    )

    print(json.dumps(dashboard.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        export_exposure_ledger_summary(summary, output_dir=args.output_dir, name=f"{args.name}_exposure_summary")
        export_position_lifecycle_report(lifecycle, output_dir=args.output_dir, name=f"{args.name}_position_lifecycle")
        export_exposure_concentration_report(concentration, output_dir=args.output_dir, name=f"{args.name}_concentration")
        export_pnl_attribution_report(pnl, output_dir=args.output_dir, name=f"{args.name}_pnl_attribution")

        path = export_portfolio_risk_dashboard(
            dashboard,
            path=Path(args.output_dir) / f"{args.name}_risk_dashboard.json",
        )

        print(f"Portfolio dashboard exported: {path}", flush=True)

    return 0 if dashboard.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())