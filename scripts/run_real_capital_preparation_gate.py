from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from real_capital_gate.gates import (
    build_micro_live_go_no_go_report,
    evaluate_emergency_shutdown_drill,
    evaluate_human_approval_record,
    evaluate_live_api_permission_audit,
    evaluate_live_credential_isolation,
    evaluate_micro_capital_risk_envelope,
    export_gate_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 32 real capital preparation gate.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--name", default="micro_live_preparation_gate")
    parser.add_argument("--output-dir", default="artifacts/real_capital_gate")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    credential = evaluate_live_credential_isolation()
    permission = evaluate_live_api_permission_audit()
    risk = evaluate_micro_capital_risk_envelope()
    approval = evaluate_human_approval_record()
    drill = evaluate_emergency_shutdown_drill()

    report = build_micro_live_go_no_go_report()

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        export_gate_json(credential, output_dir=args.output_dir, name=f"{args.name}_credential_isolation")
        export_gate_json(permission, output_dir=args.output_dir, name=f"{args.name}_api_permission_audit")
        export_gate_json(risk, output_dir=args.output_dir, name=f"{args.name}_risk_envelope")
        export_gate_json(approval, output_dir=args.output_dir, name=f"{args.name}_human_approval")
        export_gate_json(drill, output_dir=args.output_dir, name=f"{args.name}_emergency_drill")
        path = export_gate_json(report, output_dir=args.output_dir, name=f"{args.name}_go_no_go")

        print(f"Go/No-Go report exported to: {path}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())