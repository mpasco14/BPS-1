from execution.live_guard import LiveGuardConfig, LiveOrderContext, evaluate_live_order_guard


def good_context():
    return LiveOrderContext(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.01,
        price=60000,
        notional_usd=600,
        margin_usd=20,
        leverage=30,
        margin_type="ISOLATED",
        binance_allow_live_trading=True,
        risk_allow_live_trading=True,
        binance_execution_mode="live",
        safety_gate_approved=True,
        capital_ramp_approved=True,
    )


def test_live_guard_approves_valid_order():
    decision = evaluate_live_order_guard(
        context=good_context(),
        config=LiveGuardConfig(),
    )

    assert decision.approved is True
    assert decision.blockers == []


def test_live_guard_blocks_without_flags():
    context = good_context()
    context.binance_allow_live_trading = False

    decision = evaluate_live_order_guard(
        context=context,
        config=LiveGuardConfig(),
    )

    assert decision.approved is False
    assert "binance_live_flag_not_enabled" in decision.blockers


def test_live_guard_blocks_notional_above_limit():
    context = good_context()
    context.notional_usd = 1000

    decision = evaluate_live_order_guard(
        context=context,
        config=LiveGuardConfig(),
    )

    assert decision.approved is False
    assert "notional_above_limit" in decision.blockers


def test_live_guard_blocks_invalid_symbol():
    context = good_context()
    context.symbol = "ETHUSDT"

    decision = evaluate_live_order_guard(
        context=context,
        config=LiveGuardConfig(),
    )

    assert decision.approved is False
    assert "symbol_not_allowed" in decision.blockers