from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from micro_live.api_permission_audit import audit_live_api_permissions, export_live_api_permission_audit_report
from micro_live.credential_isolation import evaluate_live_credential_isolation, export_live_credential_isolation_report
from micro_live.emergency_shutdown_drill import export_emergency_shutdown_drill_report, run_emergency_shutdown_drill
from micro_live.go_no_go_report import build_micro_live_go_no_go_report, export_micro_live_go_no_go_report
from micro_live.human_approval import export_human_approval_report, evaluate_human_approval
from micro_live.risk_envelope import evaluate_micro_capital_risk_envelope, export_micro_capital_risk_envelope_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run micro-live preparation gate.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/micro_live")
    parser.add_argument("--name", default="micro_live_preparation_gate")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    credentials = evaluate_live_credential_isolation()
    permissions = audit_live_api_permissions()
    risk = evaluate_micro_capital_risk_envelope()
    approval = evaluate_human_approval()
    emergency = run_emergency_shutdown_drill()

    report = build_micro_live_go_no_go_report(
        credential_isolation=credentials,
        permission_audit=permissions,
        risk_envelope=risk,
        human_approval=approval,
        emergency_shutdown_drill=emergency,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)

        export_live_credential_isolation_report(credentials, output_dir=output_dir, name=f"{args.name}_credential_isolation")
        export_live_api_permission_audit_report(permissions, output_dir=output_dir, name=f"{args.name}_permission_audit")
        export_micro_capital_risk_envelope_report(risk, output_dir=output_dir, name=f"{args.name}_risk_envelope")
        export_human_approval_report(approval, output_dir=output_dir, name=f"{args.name}_human_approval")
        export_emergency_shutdown_drill_report(emergency, output_dir=output_dir, name=f"{args.name}_emergency_drill")
        export_micro_live_go_no_go_report(report, output_dir=output_dir, name=f"{args.name}_go_no_go")

        print(f"Micro-live preparation artifacts exported to: {output_dir}", flush=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())