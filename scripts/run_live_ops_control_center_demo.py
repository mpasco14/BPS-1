from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from live_ops.kill_switch_router import KillSwitchRequest, route_kill_switch_command, export_kill_switch_route_report
from live_ops.live_session_supervisor import LiveSessionTelemetry, supervise_live_session, export_live_session_supervisor_report
from live_ops.operator_action_audit import (
    OperatorActionRecord,
    append_operator_action_record,
    build_operator_action_audit_report,
    export_operator_action_audit_report,
)
from live_ops.operator_command_console import (
    OperatorCommandRequest,
    evaluate_operator_command,
    export_operator_command_decision,
)
from live_ops.safe_mode_controller import SafeModeRequest, evaluate_safe_mode_request, export_safe_mode_decision


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Live Ops Control Center demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/live_ops")
    parser.add_argument("--name", default="live_ops_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    command = evaluate_operator_command(
        request=OperatorCommandRequest(
            command_id="demo_cmd_1",
            command="ACTIVATE_KILL_SWITCH",
            operator="Paulo",
            environment="testnet",
            session_name="demo_session",
            reason="Demo emergency route.",
        )
    )

    safe_mode = evaluate_safe_mode_request(
        request=SafeModeRequest(
            action="ENTER_SAFE_MODE",
            operator="Paulo",
            reason="Demo safe mode activation.",
        )
    )

    kill_switch = route_kill_switch_command(
        request=KillSwitchRequest(
            command="ACTIVATE",
            operator="Paulo",
            reason="Demo kill switch activation.",
        )
    )

    supervisor = supervise_live_session(
        telemetry=LiveSessionTelemetry(
            session_name="demo_session",
            environment="testnet",
            safe_mode_active=True,
            kill_switch_active=True,
            open_orders_count=1,
            open_positions_count=1,
            drawdown_usd=2,
            rejection_rate=0.01,
            ood_rate=0.02,
        )
    )

    if args.export:
        export_operator_command_decision(command, output_dir=output_dir, name=f"{args.name}_operator_command")
        export_safe_mode_decision(safe_mode, output_dir=output_dir, name=f"{args.name}_safe_mode")
        export_kill_switch_route_report(kill_switch, output_dir=output_dir, name=f"{args.name}_kill_switch")
        export_live_session_supervisor_report(supervisor, output_dir=output_dir, name=f"{args.name}_supervisor")

        audit_path = output_dir / f"{args.name}_operator_actions.jsonl"

        append_operator_action_record(
            OperatorActionRecord(
                action_id="demo_action_1",
                operator="Paulo",
                command="ACTIVATE_KILL_SWITCH",
                status="EXECUTED",
                environment="testnet",
                session_name="demo_session",
                reason="Demo action audit.",
            ),
            path=audit_path,
        )

        audit_report = build_operator_action_audit_report(path=audit_path)
        export_operator_action_audit_report(audit_report, output_dir=output_dir, name=f"{args.name}_audit")

    payload = {
        "operator_command": command.model_dump(mode="json"),
        "safe_mode": safe_mode.model_dump(mode="json"),
        "kill_switch": kill_switch.model_dump(mode="json"),
        "supervisor": supervisor.model_dump(mode="json"),
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())