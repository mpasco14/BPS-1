from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from release_management.deployment_promotion import (
    DeploymentPromotionInputs,
    evaluate_deployment_promotion,
    export_deployment_promotion_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate deployment promotion.")

    parser.add_argument("--version", default="0.17.0")
    parser.add_argument("--current-stage", default="dev")
    parser.add_argument("--target-stage", default="paper")

    parser.add_argument("--live-approved", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/release")
    parser.add_argument("--name", default="deployment_promotion_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    report = evaluate_deployment_promotion(
        inputs=DeploymentPromotionInputs(
            release_version=args.version,
            current_stage=args.current_stage,
            target_stage=args.target_stage,
            release_candidate_passed=True,
            quality_gate_passed=True,
            security_passed=True,
            infra_passed=True,
            paper_validated=True,
            testnet_validated=args.live_approved,
            micro_live_validated=False,
            production_guard_passed=args.live_approved,
            emergency_test_passed=args.live_approved,
            human_approval_valid=args.live_approved,
        )
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_deployment_promotion_report(report, output_dir=args.output_dir, name=args.name)
        print(f"Deployment promotion exported: {path}", flush=True)

    return 0 if report.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())