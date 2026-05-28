from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from v1_acceptance.operator_checklist import (
    build_v1_operator_checklist,
    evaluate_operator_checklist,
    export_operator_checklist_report,
)
from v1_acceptance.v1_acceptance_report import (
    build_v1_acceptance_report,
    component_from_report,
    export_v1_acceptance_report,
)
from v1_acceptance.v1_contracts import (
    build_default_v1_contract_bundle,
    evaluate_v1_contracts,
    export_v1_contract_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V1 acceptance demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/v1_acceptance")
    parser.add_argument("--name", default="v1_acceptance_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    contracts = evaluate_v1_contracts(
        contracts=build_default_v1_contract_bundle()
    )

    checklist = evaluate_operator_checklist(
        checklist=build_v1_operator_checklist(
            operator="Paulo",
            mark_demo_passed=True,
        )
    )

    components = [
        component_from_report(name="pytest", passed=True, status="PASS", evidence_path="pytest"),
        component_from_report(name="e2e", passed=True, status="PASS", evidence_path="artifacts/e2e/e2e_full_system_report.json"),
        component_from_report(name="scenario_testing", passed=True, status="PASS", evidence_path="artifacts/scenario_testing/scenario_testing_full_report.json"),
        component_from_report(name="testnet_acceptance", passed=True, status="ACCEPTED", evidence_path="artifacts/testnet_readiness/testnet_readiness_demo_acceptance.json"),
        component_from_report(name="security", passed=True, status="PASS", evidence_path="artifacts/security"),
        component_from_report(name="docs", passed=True, status="PASS", evidence_path="docs/"),
    ]

    report = build_v1_acceptance_report(
        contracts_report=contracts,
        operator_checklist_report=checklist,
        components=components,
        metadata={"demo": True},
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)

        export_v1_contract_report(
            contracts,
            output_dir=output_dir,
            name=f"{args.name}_contracts",
        )

        export_operator_checklist_report(
            checklist,
            output_dir=output_dir,
            name=f"{args.name}_operator_checklist",
        )

        export_v1_acceptance_report(
            report,
            path=output_dir / f"{args.name}_report.json",
        )

        print(f"V1 acceptance artifacts exported to: {output_dir}", flush=True)

    return 0 if report.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())