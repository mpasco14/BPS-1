from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from execution.live_order_adapter import LiveOrderAdapterConfig, LiveOrderRequest, submit_live_order
from ops.emergency_stop_procedure_test import EmergencyStopProcedureInputs, build_emergency_stop_procedure_report
from ops.human_approval_workflow import (
    HumanApprovalDecision,
    create_human_approval_request,
    validate_human_approval,
)
from ops.production_environment_guard import (
    ProductionEnvironmentInputs,
    evaluate_production_environment_guard,
)
from ops.secrets_key_rotation_audit import SecretKeyRecord, build_secrets_key_rotation_audit_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run production readiness demo.")
    return parser.parse_args()


def main() -> int:
    _ = parse_args()

    secrets = build_secrets_key_rotation_audit_report(
        secrets=[
            SecretKeyRecord(
                name="BINANCE_API_KEY",
                present=True,
                storage_backend="vault",
                last_rotated_at=datetime.now(timezone.utc),
                permissions=["read", "trade"],
            ),
            SecretKeyRecord(
                name="BINANCE_API_SECRET",
                present=True,
                storage_backend="vault",
                last_rotated_at=datetime.now(timezone.utc),
                permissions=["read", "trade"],
            ),
        ]
    )

    approval_request = create_human_approval_request(
        approval_id="demo_approval",
        requested_action="controlled_live_activation",
        reason="Demo readiness validation.",
        approver="Paulo",
    )

    approval_report = validate_human_approval(
        request=approval_request,
        decision=HumanApprovalDecision(
            approval_id="demo_approval",
            approver="Paulo",
            approved=True,
            confirmation_phrase="I_APPROVE_CONTROLLED_LIVE_ACTIVATION",
        ),
    )

    emergency = build_emergency_stop_procedure_report(
        inputs=EmergencyStopProcedureInputs(
            kill_switch_activated=True,
            cancel_all_orders_called=True,
            open_orders_after_cancel=0,
            new_orders_blocked=True,
            safe_mode_active=True,
            notification_sent=True,
        )
    )

    guard = evaluate_production_environment_guard(
        inputs=ProductionEnvironmentInputs(
            testnet_passed=True,
            live_preflight_passed=True,
            live_risk_audit_passed=True,
            capital_ramp_validated=True,
            secrets_audit_passed=secrets.passed,
            human_approval_valid=approval_report.valid,
            emergency_state_clear=emergency.passed,
        )
    )

    live_order = submit_live_order(
        request=LiveOrderRequest(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.001,
            price=60000,
            notional_usd=60,
            margin_usd=2,
            leverage=30,
            production_guard_passed=guard.passed,
            secrets_audit_passed=secrets.passed,
            live_risk_audit_passed=True,
            capital_ramp_validated=True,
            human_approval_valid=approval_report.valid,
            emergency_clear=emergency.passed,
            confirmation_phrase="I_ACCEPT_LIVE_RISK",
        ),
        config=LiveOrderAdapterConfig(
            enabled=True,
            dry_run=True,
            allow_submission=False,
        ),
    )

    output = {
        "secrets": secrets.model_dump(mode="json"),
        "approval": approval_report.model_dump(mode="json"),
        "emergency": emergency.model_dump(mode="json"),
        "production_guard": guard.model_dump(mode="json"),
        "live_order_adapter": live_order.model_dump(mode="json"),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))

    return 0 if guard.passed and secrets.passed and approval_report.valid and emergency.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())