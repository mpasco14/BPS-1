from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from testnet_campaign.campaign_models import LongTestnetCampaignConfig
from testnet_campaign.long_campaign_runner import (
    export_long_testnet_campaign_report,
    run_long_testnet_campaign,
)


SESSION_PRESETS = {
    "30min": {
        "duration_minutes": 30,
        "interval_seconds": 600,
        "max_iterations": 3,
    },
    "2h": {
        "duration_minutes": 120,
        "interval_seconds": 1200,
        "max_iterations": 6,
    },
    "6h": {
        "duration_minutes": 360,
        "interval_seconds": 1800,
        "max_iterations": 12,
    },
    "12h": {
        "duration_minutes": 720,
        "interval_seconds": 3600,
        "max_iterations": 12,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run long real Binance Futures Testnet campaign.")

    parser.add_argument("--session", choices=SESSION_PRESETS.keys(), required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--quantity", type=float, default=0.001)
    parser.add_argument("--price", type=float, default=60000.0)

    parser.add_argument("--real-testnet", action="store_true")
    parser.add_argument("--allow-submit", action="store_true")
    parser.add_argument("--allow-cancel", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--no-sleep", action="store_true", help="For tests only. Do not use for real campaign.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    preset = SESSION_PRESETS[args.session]
    campaign_name = args.name or f"real_campaign_{args.session}"

    config = LongTestnetCampaignConfig(
        campaign_name=campaign_name,
        symbol=args.symbol,
        duration_minutes=preset["duration_minutes"],
        interval_seconds=preset["interval_seconds"],
        max_iterations=preset["max_iterations"],
        quantity=args.quantity,
        price=args.price,
        require_real_mode=args.real_testnet,
        allow_real_submit=args.allow_submit,
        allow_real_cancel=args.allow_cancel,
    )

    report = run_long_testnet_campaign(
        config=config,
        sleep_between_iterations=not args.no_sleep,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_long_testnet_campaign_report(report, name=campaign_name)
        print(f"Campaign report exported to: {path}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())