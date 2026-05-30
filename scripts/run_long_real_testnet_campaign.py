from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from testnet_campaign.campaign_models import LongTestnetCampaignConfig, load_long_testnet_campaign_config
from testnet_campaign.campaign_runner import export_campaign_session_result, run_campaign_sessions
from testnet_campaign.multi_session_review import export_multi_session_campaign_review, review_multi_session_campaign
from testnet_campaign.session_plans import build_campaign_session_plan, build_default_campaign_session_plans


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run long real/simulated testnet campaign.")

    parser.add_argument("--session", choices=["all", "30min", "2h", "6h", "12h"], default="all")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--real-testnet", action="store_true")
    parser.add_argument("--allow-submit", action="store_true")
    parser.add_argument("--allow-cancel", action="store_true")
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/testnet_campaign")
    parser.add_argument("--name", default="long_testnet_campaign")

    return parser.parse_args()


def duration_from_session_arg(value: str) -> int | None:
    mapping = {
        "30min": 30,
        "2h": 120,
        "6h": 360,
        "12h": 720,
    }

    return mapping.get(value)


def build_config_from_args(args: argparse.Namespace) -> LongTestnetCampaignConfig:
    base = load_long_testnet_campaign_config()

    simulate = base.simulate

    if args.simulate:
        simulate = True

    if args.real_testnet:
        simulate = False

    return base.model_copy(
        update={
            "simulate": simulate,
            "allow_real_submit": args.allow_submit if args.allow_submit else base.allow_real_submit,
            "allow_real_cancel": args.allow_cancel if args.allow_cancel else base.allow_real_cancel,
        }
    )


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    config = build_config_from_args(args)

    if args.session == "all":
        plans = build_default_campaign_session_plans(config=config)
    else:
        duration = duration_from_session_arg(args.session)
        plans = [
            build_campaign_session_plan(
                duration_minutes=duration,
                session_name=f"{args.name}_{args.session}",
                config=config,
            )
        ]

    results = run_campaign_sessions(
        plans=plans,
        config=config,
        stop_on_failure=args.stop_on_failure,
    )

    review = review_multi_session_campaign(
        sessions=results,
        config=config,
    )

    print(json.dumps(review.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)

        for result in results:
            export_campaign_session_result(
                result,
                output_dir=output_dir,
                name=f"{args.name}_{result.duration_minutes}min_session",
            )

        export_multi_session_campaign_review(
            review,
            output_dir=output_dir,
            name=f"{args.name}_review",
        )

        print(f"Long testnet campaign artifacts exported to: {output_dir}", flush=True)

    return 0 if review.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())