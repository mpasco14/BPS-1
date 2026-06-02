from real_capital_gate.gates import (
    build_micro_live_go_no_go_report,
    evaluate_emergency_shutdown_drill,
    evaluate_human_approval_record,
    evaluate_live_api_permission_audit,
    evaluate_live_credential_isolation,
    evaluate_micro_capital_risk_envelope,
)


def test_live_credential_isolation_blocks_live_submit(monkeypatch):
    monkeypatch.setenv("BINANCE_LIVE_REST_BASE_URL", "https://fapi.binance.com")
    monkeypatch.setenv("BINANCE_LIVE_ALLOW_ORDER_SUBMISSION", "true")
    monkeypatch.setenv("BINANCE_LIVE_ALLOW_CANCEL_ORDERS", "false")

    report = evaluate_live_credential_isolation()

    assert report.passed is False
    assert "live_order_submission_must_be_disabled_at_gate" in report.blockers


def test_live_api_permission_audit_blocks_withdrawal(monkeypatch):
    monkeypatch.setenv("BINANCE_LIVE_API_ENABLE_READING", "true")
    monkeypatch.setenv("BINANCE_LIVE_API_ENABLE_FUTURES", "true")
    monkeypatch.setenv("BINANCE_LIVE_API_ENABLE_WITHDRAWALS", "true")
    monkeypatch.setenv("BINANCE_LIVE_API_ENABLE_INTERNAL_TRANSFER", "false")

    report = evaluate_live_api_permission_audit()

    assert report.passed is False
    assert "withdrawals_permission_must_be_disabled" in report.blockers


def test_micro_capital_risk_envelope_blocks_large_capital(monkeypatch):
    monkeypatch.setenv("MICRO_LIVE_MAX_CAPITAL_USD", "500")

    report = evaluate_micro_capital_risk_envelope()

    assert report.passed is False
    assert "micro_capital_above_safe_limit" in report.blockers


def test_human_approval_requires_operator(monkeypatch):
    monkeypatch.setenv("MICRO_LIVE_OPERATOR_NAME", "")
    monkeypatch.setenv("MICRO_LIVE_APPROVAL_TEXT", "")

    report = evaluate_human_approval_record()

    assert report.passed is False
    assert "operator_name_required" in report.blockers
    assert "approval_text_required" in report.blockers


def test_emergency_shutdown_drill_blocks_missing_cancel_all(monkeypatch):
    monkeypatch.setenv("EMERGENCY_DRILL_CANCEL_ALL_AVAILABLE", "false")

    report = evaluate_emergency_shutdown_drill()

    assert report.passed is False
    assert "cancel_all_orders_route_unavailable" in report.blockers


def test_go_no_go_can_pass_with_all_declarations(monkeypatch):
    monkeypatch.setenv("BINANCE_LIVE_REST_BASE_URL", "https://fapi.binance.com")
    monkeypatch.setenv("BINANCE_LIVE_ALLOW_ORDER_SUBMISSION", "false")
    monkeypatch.setenv("BINANCE_LIVE_ALLOW_CANCEL_ORDERS", "false")

    monkeypatch.setenv("BINANCE_LIVE_API_ENABLE_READING", "true")
    monkeypatch.setenv("BINANCE_LIVE_API_ENABLE_FUTURES", "true")
    monkeypatch.setenv("BINANCE_LIVE_API_ENABLE_WITHDRAWALS", "false")
    monkeypatch.setenv("BINANCE_LIVE_API_ENABLE_INTERNAL_TRANSFER", "false")
    monkeypatch.setenv("BINANCE_LIVE_API_IP_RESTRICTED", "true")

    monkeypatch.setenv("MICRO_LIVE_OPERATOR_NAME", "Paulo")
    monkeypatch.setenv("MICRO_LIVE_APPROVAL_TEXT", "Aprovo apenas preparação para live read-only, sem envio de ordem.")
    monkeypatch.setenv("MICRO_LIVE_APPROVE_TESTNET_REVIEW_PASSED", "true")
    monkeypatch.setenv("MICRO_LIVE_APPROVE_READONLY_LIVE_ONLY", "true")
    monkeypatch.setenv("MICRO_LIVE_APPROVE_NO_WITHDRAWAL_PERMISSION", "true")
    monkeypatch.setenv("MICRO_LIVE_APPROVE_MICRO_CAPITAL_LIMITS", "true")
    monkeypatch.setenv("MICRO_LIVE_APPROVE_KILL_SWITCH_READY", "true")
    monkeypatch.setenv("MICRO_LIVE_APPROVE_NO_FINANCIAL_ADVICE", "true")

    report = build_micro_live_go_no_go_report()

    assert report.passed is True
    assert report.decision in {"GO", "HOLD"}