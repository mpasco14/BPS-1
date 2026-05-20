from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.live_preflight import (
    LivePreflightInputs,
    build_live_preflight_report,
    export_live_preflight_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live preflight checklist.")

    parser.add_argument("--live-safety-passed", action="store_true")
    parser.add_argument("--capital-ramp-passed", action="store_true")
    parser.add_argument("--deployment-readiness-passed", action="store_true")
    parser.add_argument("--testnet-warmup-passed", action="store_true")
    parser.add_argument("--testnet-continuous-passed", action="store_true")
    parser.add_argument("--risk-state-ok", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/ops")
    parser.add_argument("--name", default="live_preflight_latest")

    return parser.parse_args()


def maybe_inputs_from_args(args: argparse.Namespace) -> LivePreflightInputs | None:
    has_override = (
        args.live_safety_passed
        or args.capital_ramp_passed
        or args.deployment_readiness_passed
        or args.testnet_warmup_passed
        or args.testnet_continuous_passed
        or args.risk_state_ok
    )

    if not has_override:
        return None

    return LivePreflightInputs(
        live_safety_passed=True if args.live_safety_passed else None,
        capital_ramp_passed=True if args.capital_ramp_passed else None,
        deployment_readiness_passed=True if args.deployment_readiness_passed else None,
        testnet_warmup_passed=True if args.testnet_warmup_passed else None,
        testnet_continuous_passed=True if args.testnet_continuous_passed else None,
        emergency_safe_mode_active=False,
        risk_state_status="OK" if args.risk_state_ok else None,
        risk_state_blockers=[],
        binance_allow_live_trading=False,
        risk_allow_live_trading=False,
        binance_execution_mode="paper",
    )


def main() -> int:
    args = parse_args()

    report = build_live_preflight_report(
        inputs=maybe_inputs_from_args(args),
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_live_preflight_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Live preflight exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())