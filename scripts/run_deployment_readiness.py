"""
Run deployment readiness gate.

Exemplos:

    python scripts/run_deployment_readiness.py --stage testnet
    python scripts/run_deployment_readiness.py --stage live
    python scripts/run_deployment_readiness.py --stage testnet --export --name readiness_demo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.deployment_readiness import (
    DeploymentReadinessInputs,
    build_deployment_readiness_report,
    export_deployment_readiness_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BTC Binance Futures deployment readiness gate."
    )

    parser.add_argument("--stage", choices=["paper", "testnet", "live"], default=None)

    parser.add_argument("--security-passed", action="store_true")
    parser.add_argument("--compliance-passed", action="store_true")
    parser.add_argument("--runbook-passed", action="store_true")
    parser.add_argument("--testnet-warmup-passed", action="store_true")
    parser.add_argument("--legal-review-approved", action="store_true")
    parser.add_argument("--emergency-safe-mode-active", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", type=str, default="artifacts/ops")
    parser.add_argument("--name", type=str, default="deployment_readiness_latest")

    return parser.parse_args()


def maybe_build_inputs_from_args(args: argparse.Namespace) -> DeploymentReadinessInputs | None:
    has_override = (
        args.security_passed
        or args.compliance_passed
        or args.runbook_passed
        or args.testnet_warmup_passed
        or args.legal_review_approved
        or args.emergency_safe_mode_active
    )

    if not has_override:
        return None

    return DeploymentReadinessInputs(
        security_passed=True if args.security_passed else None,
        compliance_passed=True if args.compliance_passed else None,
        compliance_blocking_fail_count=0 if args.compliance_passed else 1,
        runbook_passed=True if args.runbook_passed else None,
        testnet_warmup_passed=True if args.testnet_warmup_passed else None,
        emergency_safe_mode_active=args.emergency_safe_mode_active,
        legal_review_approved=args.legal_review_approved,
    )


def main() -> int:
    args = parse_args()

    inputs = maybe_build_inputs_from_args(args)

    report = build_deployment_readiness_report(
        stage=args.stage,
        inputs=inputs,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_deployment_readiness_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )

        print(f"Deployment readiness report exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())