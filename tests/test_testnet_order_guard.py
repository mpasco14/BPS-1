from execution.binance_testnet_client import BinanceTestnetConfig
from execution.testnet_order_guard import (
    TestnetOrderContext,
    TestnetOrderGuardConfig,
    build_context_from_testnet_config,
    evaluate_testnet_order_guard,
)


def good_context():
    return TestnetOrderContext(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.01,
        notional_usd=600,
        price=60000,
        testnet_ready=True,
        testnet_allow_order_submission=True,
    )


def test_testnet_order_guard_approves_good_context():
    decision = evaluate_testnet_order_guard(
        context=good_context(),
        config=TestnetOrderGuardConfig(),
    )

    assert decision.approved is True


def test_testnet_order_guard_blocks_submission_flag():
    context = good_context()
    context.testnet_allow_order_submission = False

    decision = evaluate_testnet_order_guard(
        context=context,
        config=TestnetOrderGuardConfig(),
    )

    assert decision.approved is False
    assert "testnet_order_submission_not_allowed" in decision.blockers


def test_build_context_from_testnet_config():
    context = build_context_from_testnet_config(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.01,
        notional_usd=600,
        testnet_config=BinanceTestnetConfig(
            enabled=True,
            api_key="key",
            api_secret="secret",
            allow_order_submission=True,
        ),
    )

    assert context.testnet_ready is True
    assert context.testnet_allow_order_submission is True