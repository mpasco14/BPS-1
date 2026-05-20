from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.governance import GovernanceEvidence, evaluate_governance, export_governance_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run system governance check.")

    parser.add_argument("--all-ready", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/governance")
    parser.add_argument("--name", default="governance_latest")

    return parser.parse_args()


def build_evidence(args: argparse.Namespace) -> GovernanceEvidence:
    if args.all_ready:
        return GovernanceEvidence(
            model_available=True,
            calibration_available=True,
            ood_detection_available=True,
            feedback_dataset_available=True,
            decision_journal_available=True,
            order_lifecycle_available=True,
            audit_reports_available=True,
            model_registry_available=True,
            risk_manager_available=True,
            live_guard_available=True,
            capital_ramp_available=True,
            preflight_available=True,
            live_disabled_by_default=True,
            secrets_not_committed=True,
            testnet_separated=True,
            compliance_available=True,
            kill_switch_available=True,
            emergency_shutdown_available=True,
            health_checks_available=True,
            alerting_available=True,
        )

    return GovernanceEvidence()


def main() -> int:
    args = parse_args()

    report = evaluate_governance(evidence=build_evidence(args))

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_governance_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Governance report exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())