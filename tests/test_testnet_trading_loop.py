from execution.testnet_trading_loop import (
    ControlledTestnetTradeRequest,
    run_controlled_testnet_trade,
)


def test_controlled_testnet_trade_dry_run():
    result = run_controlled_testnet_trade(
        request=ControlledTestnetTradeRequest(
            session_name="unit",
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.001,
            price=10000,
            notional_usd=10,
            dry_run=True,
        )
    )

    assert result.status == "DRY_RUN"
    assert result.approved is True
    assert result.session_report is not None


def test_controlled_testnet_trade_blocks_large_notional():
    result = run_controlled_testnet_trade(
        request=ControlledTestnetTradeRequest(
            session_name="unit",
            symbol="BTCUSDT",
            side="BUY",
            quantity=1,
            price=10000,
            notional_usd=10000,
            dry_run=True,
        )
    )

    assert result.status == "BLOCKED"
    assert result.approved is False