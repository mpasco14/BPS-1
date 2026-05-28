from binance_testnet_adapter.account_snapshot import fetch_binance_testnet_account_snapshot
from binance_testnet_adapter.position_reconciliation import reconcile_binance_testnet_position
from testnet_readiness.testnet_portfolio_reconciliation import build_flat_position


def test_binance_testnet_position_reconciliation_flat_passes():
    account = fetch_binance_testnet_account_snapshot(symbol="BTCUSDT")

    report = reconcile_binance_testnet_position(
        local_position=build_flat_position("BTCUSDT"),
        account_snapshot=account,
        symbol="BTCUSDT",
    )

    assert report.passed is True
    assert report.status == "PASS"