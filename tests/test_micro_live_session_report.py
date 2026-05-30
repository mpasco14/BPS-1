from micro_live.go_no_go_report import build_micro_live_go_no_go_report
from micro_live.api_permission_audit import LiveAPIPermissionAuditConfig, audit_live_api_permissions
from micro_live.credential_isolation import LiveCredentialIsolationConfig, evaluate_live_credential_isolation
from micro_live.emergency_shutdown_drill import EmergencyShutdownDrillConfig, run_emergency_shutdown_drill
from micro_live.human_approval import HumanApprovalConfig, evaluate_human_approval
from micro_live.risk_envelope import MicroCapitalRiskEnvelopeConfig, evaluate_micro_capital_risk_envelope
from micro_live_session.dry_run_signal import MicroLiveDryRunSignalInput
from micro_live_session.session_models import MicroLiveSessionConfig
from micro_live_session.session_report import build_micro_live_session_report


def passing_go_no_go(monkeypatch, tmp_path):
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")

    credentials = evaluate_live_credential_isolation(
        config=LiveCredentialIsolationConfig(
            require_live_keys=True,
            live_api_key="live",
            live_api_secret="live_secret",
            testnet_api_key="testnet",
            testnet_api_secret="testnet_secret",
        )
    )
    permissions = audit_live_api_permissions(config=LiveAPIPermissionAuditConfig())
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

    return build_micro_live_go_no_go_report(
        credential_isolation=credentials,
        permission_audit=permissions,
        risk_envelope=risk,
        human_approval=approval,
        emergency_shutdown_drill=emergency,
    )


def test_micro_live_session_report_dry_run_passes(monkeypatch, tmp_path):
    gate = passing_go_no_go(monkeypatch, tmp_path)

    report = build_micro_live_session_report(
        go_no_go_report=gate,
        signal_input=MicroLiveDryRunSignalInput(confidence=0.8, edge_pct=0.003),
        config=MicroLiveSessionConfig(
            dry_run=True,
            allow_live_order=False,
            quantity=0.001,
            price=6000,
            max_notional_usd=10,
            emergency_stop_file=tmp_path / "session_stop.flag",
        ),
    )

    assert report.passed is True
    assert report.decision == "DRY_RUN_ONLY"
    assert report.final_flat is True