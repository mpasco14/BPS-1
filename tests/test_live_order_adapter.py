from execution.live_order_adapter import (
    LiveOrderAdapterConfig,
    LiveOrderRequest,
    submit_live_order,
)


def good_request():
    return LiveOrderRequest(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        price=60000,
        notional_usd=60,
        margin_usd=2,
        leverage=30,
        production_guard_passed=True,
        secrets_audit_passed=True,
        live_risk_audit_passed=True,
        capital_ramp_validated=True,
        human_approval_valid=True,
        emergency_clear=True,
        confirmation_phrase="I_ACCEPT_LIVE_RISK",
    )


def test_live_order_adapter_blocks_by_default():
    decision = submit_live_order(request=good_request())

    assert decision.status == "BLOCKED"
    assert "live_order_adapter_disabled" in decision.blockers


def test_live_order_adapter_dry_run_when_enabled():
    decision = submit_live_order(
        request=good_request(),
        config=LiveOrderAdapterConfig(
            enabled=True,
            dry_run=True,
            allow_submission=False,
        ),
    )

    assert decision.status == "BLOCKED"
    assert "live_order_submission_not_allowed" in decision.blockers


def test_live_order_adapter_can_submit_with_mock_client():
    response = {"orderId": "unit-order"}

    decision = submit_live_order(
        request=good_request(),
        config=LiveOrderAdapterConfig(
            enabled=True,
            dry_run=False,
            allow_submission=True,
        ),
        client_submit_order=lambda payload: response,
    )

    assert decision.status == "SUBMITTED"
    assert decision.submitted is True
    assert decision.exchange_response == response