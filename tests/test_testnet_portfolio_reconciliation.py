from testnet_readiness.testnet_portfolio_reconciliation import (
    TestnetPositionSnapshot,
    build_flat_position,
    reconcile_testnet_portfolio,
)


def test_testnet_portfolio_reconciliation_flat_passes():
    report = reconcile_testnet_portfolio(
        local_position=build_flat_position(),
        exchange_position=build_flat_position(),
    )

    assert report.passed is True
    assert report.local_flat is True
    assert report.exchange_flat is True


def test_testnet_portfolio_reconciliation_blocks_qty_diff():
    report = reconcile_testnet_portfolio(
        local_position=TestnetPositionSnapshot(symbol="BTCUSDT", side="LONG", quantity=0.001, notional_usd=60),
        exchange_position=build_flat_position(),
    )

    assert report.passed is False
    assert "side_mismatch" in report.blockers
    assert "position_qty_diff_above_limit" in report.blockers