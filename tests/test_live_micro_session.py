from execution.live_micro_session import (
    LiveMicroSessionConfig,
    LiveMicroTradeRequest,
    run_live_micro_session,
)


def good_request():
    return LiveMicroTradeRequest(
        session_name="unit",
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.01,
        price=60000,
        notional_usd=600,
        margin_usd=20,
        leverage=30,
        safety_gate_approved=True,
        capital_ramp_approved=True,
        live_preflight_passed=True,
        binance_allow_live_trading=True,
        risk_allow_live_trading=True,
        binance_execution_mode="live",
    )


def test_live_micro_session_blocked_when_disabled():
    result = run_live_micro_session(
        request=good_request(),
        config=LiveMicroSessionConfig(enabled=False),
    )

    assert result.status == "BLOCKED"
    assert "live_micro_session_disabled" in result.blockers


def test_live_micro_session_dry_run_when_enabled_but_submission_disabled():
    result = run_live_micro_session(
        request=good_request(),
        config=LiveMicroSessionConfig(
            enabled=True,
            dry_run=True,
            allow_order_submission=False,
        ),
    )

    assert result.status == "DRY_RUN"
    assert result.approved is True
    assert result.submitted is False


def test_live_micro_session_blocks_above_notional():
    request = good_request()
    request.notional_usd = 1000

    result = run_live_micro_session(
        request=request,
        config=LiveMicroSessionConfig(enabled=True),
    )

    assert result.status == "BLOCKED"
    assert "micro_notional_above_limit" in result.blockers