from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from testnet_supervision.credential_readiness import (
    evaluate_testnet_credential_readiness,
    export_testnet_credential_readiness_report,
)
from testnet_supervision.long_testnet_runner import (
    LongTestnetRunnerConfig,
    export_long_testnet_runner_report,
    run_controlled_long_testnet_session,
)
from testnet_supervision.session_review_gate import (
    export_testnet_session_review_gate_report,
    review_testnet_session_for_promotion,
)
from testnet_supervision.supervised_session_plan import (
    build_supervised_testnet_session_plan,
    evaluate_supervised_testnet_session_plan,
    export_supervised_testnet_session_plan_report,
)
from testnet_supervision.testnet_evidence_collector import export_testnet_evidence_collection_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run supervised long testnet validation session.")

    parser.add_argument("--session-name", default="v1_rc1_supervised_testnet")
    parser.add_argument("--duration-minutes", type=int, default=30)
    parser.add_argument("--operator", default="Paulo")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--real-testnet-placeholder", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/testnet_supervision")
    parser.add_argument("--name", default="supervised_testnet_session")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    credentials = evaluate_testnet_credential_readiness(
        metadata={"script": "run_testnet_supervised_session"}
    )

    plan = build_supervised_testnet_session_plan(
        session_name=args.session_name,
        duration_minutes=args.duration_minutes,
        operator=args.operator,
        metadata={"script": "run_testnet_supervised_session"},
    )

    plan_report = evaluate_supervised_testnet_session_plan(
        plan=plan,
        credential_readiness=credentials,
    )

    simulate = True
    if args.real_testnet_placeholder:
        simulate = False
    if args.simulate:
        simulate = True

    runner = run_controlled_long_testnet_session(
        plan=plan,
        credential_readiness=credentials,
        config=LongTestnetRunnerConfig(simulate=simulate),
        metadata={"script": "run_testnet_supervised_session"},
    )

    review = review_testnet_session_for_promotion(
        credential_readiness=credentials,
        session_plan=plan_report,
        runner=runner,
        evidence=runner.evidence,
    )

    print(json.dumps(review.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)

        export_testnet_credential_readiness_report(
            credentials,
            output_dir=output_dir,
            name=f"{args.name}_credential_readiness",
        )
        export_supervised_testnet_session_plan_report(
            plan_report,
            output_dir=output_dir,
            name=f"{args.name}_session_plan",
        )
        export_long_testnet_runner_report(
            runner,
            output_dir=output_dir,
            name=f"{args.name}_runner",
        )
        export_testnet_evidence_collection_report(
            runner.evidence,
            output_dir=output_dir,
            name=f"{args.name}_evidence",
        )
        export_testnet_session_review_gate_report(
            review,
            output_dir=output_dir,
            name=f"{args.name}_review_gate",
        )

        print(f"Supervised testnet artifacts exported to: {output_dir}", flush=True)

    return 0 if review.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())