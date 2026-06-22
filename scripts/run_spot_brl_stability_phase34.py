from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from spot_micro_live.phase34_stability import (
    build_fee_dust_accounting,
    build_fill_risk_slippage_review,
    build_reconciliation_audit,
    build_stability_campaign_report,
    export_json,
    load_phase34_config,
    run_emergency_cancel_all_drill,
    run_repeat_micro_live_submit_cancel_x3,
)


from spot_micro_live.phase34_stability import (
    build_fee_dust_accounting,
    build_fill_risk_slippage_review,
    build_reconciliation_audit,
    build_stability_campaign_report,
    export_json,
    load_phase34_config,
    run_emergency_cancel_all_drill,
    run_repeat_micro_live_submit_cancel_x3,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Phase 34 Spot BRL micro-live stability campaign."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "repeat-x3",
            "reconciliation-audit",
            "fee-dust",
            "fill-risk",
            "emergency-drill",
            "report",
        ],
    )
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--name", default=None)

    args = parser.parse_args()

    config = load_phase34_config()

    if args.mode == "repeat-x3":
        report = run_repeat_micro_live_submit_cancel_x3(config)
        name = args.name or "repeat_submit_cancel_x3"

    elif args.mode == "reconciliation-audit":
        report = build_reconciliation_audit(config)
        name = args.name or "post_order_reconciliation_audit"

    elif args.mode == "fee-dust":
        report = build_fee_dust_accounting(config)
        name = args.name or "brl_fee_dust_accounting"

    elif args.mode == "fill-risk":
        report = build_fill_risk_slippage_review(config)
        name = args.name or "fill_risk_slippage_review"

    elif args.mode == "emergency-drill":
        report = run_emergency_cancel_all_drill(config)
        name = args.name or "emergency_cancel_all_drill"

    elif args.mode == "report":
        report = build_stability_campaign_report(config)
        name = args.name or "stability_campaign_report"

    else:
        raise ValueError(f"Unsupported mode: {args.mode}")

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        output_path = export_json(report, output_dir=config.output_dir, name=name)
        print(f"Report exported to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())