from micro_live.api_permission_audit import LiveAPIPermissionAuditConfig, audit_live_api_permissions
from micro_live.credential_isolation import LiveCredentialIsolationConfig, evaluate_live_credential_isolation
from micro_live.emergency_shutdown_drill import EmergencyShutdownDrillConfig, run_emergency_shutdown_drill
from micro_live.go_no_go_report import build_micro_live_go_no_go_report
from micro_live.human_approval import HumanApprovalConfig, evaluate_human_approval
from micro_live.risk_envelope import MicroCapitalRiskEnvelopeConfig, evaluate_micro_capital_risk_envelope


def force_safe_env(monkeypatch):
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")


def test_go_no_go_blocks_missing_human_approval(monkeypatch, tmp_path):
    force_safe_env(monkeypatch)

    credentials = evaluate_live_credential_isolation(
        config=LiveCredentialIsolationConfig(require_live_keys=False)
    )
    permissions = audit_live_api_permissions(
        config=LiveAPIPermissionAuditConfig()
    )
    risk = evaluate_micro_capital_risk_envelope(
        config=MicroCapitalRiskEnvelopeConfig(max_capital_usd=25, max_order_notional_usd=10, max_daily_loss_usd=2)
    )
    approval = evaluate_human_approval(
        config=HumanApprovalConfig(operator_name="", approval_text="")
    )
    emergency = run_emergency_shutdown_drill(
        config=EmergencyShutdownDrillConfig(emergency_stop_file=tmp_path / "stop.flag")
    )

    report = build_micro_live_go_no_go_report(
        credential_isolation=credentials,
        permission_audit=permissions,
        risk_envelope=risk,
        human_approval=approval,
        emergency_shutdown_drill=emergency,
    )

    assert report.passed is False
    assert report.status == "NO_GO"


def test_go_no_go_approves_when_all_components_pass(monkeypatch, tmp_path):
    force_safe_env(monkeypatch)

    credentials = evaluate_live_credential_isolation(
        config=LiveCredentialIsolationConfig(
            require_live_keys=True,
            live_api_key="live_key",
            live_api_secret="live_secret",
            testnet_api_key="testnet_key",
            testnet_api_secret="testnet_secret",
        )
    )
    permissions = audit_live_api_permissions(
        config=LiveAPIPermissionAuditConfig(
            futures_trading_permission=True,
            withdrawals_permission=False,
            universal_transfer_permission=False,
            ip_restricted=True,
            read_only=False,
        )
    )
    risk = evaluate_micro_capital_risk_envelope(
        config=MicroCapitalRiskEnvelopeConfig(
            max_capital_usd=25,
            max_order_notional_usd=10,
            max_daily_loss_usd=2,
            max_leverage=3,
            max_orders_per_session=1,
        )
    )
    approval = evaluate_human_approval(
        config=HumanApprovalConfig(
            operator_name="Paulo",
            approval_text="I APPROVE MICRO LIVE",
            approval_phrase="I APPROVE MICRO LIVE",
        )
    )
    emergency = run_emergency_shutdown_drill(
        config=EmergencyShutdownDrillConfig(emergency_stop_file=tmp_path / "stop.flag")
    )

    report = build_micro_live_go_no_go_report(
        credential_isolation=credentials,
        permission_audit=permissions,
        risk_envelope=risk,
        human_approval=approval,
        emergency_shutdown_drill=emergency,
    )

    assert report.passed is True
    assert report.decision == "APPROVED_FOR_MICRO_LIVE_SESSION"