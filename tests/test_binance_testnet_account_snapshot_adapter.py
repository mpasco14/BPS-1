from binance_testnet_adapter.account_snapshot import fetch_binance_testnet_account_snapshot


def test_binance_testnet_account_snapshot_simulated_passes():
    report = fetch_binance_testnet_account_snapshot(symbol="BTCUSDT")

    assert report.passed is True
    assert report.simulated is True
    assert report.usdt_balance is not None
    assert report.positions[0]["symbol"] == "BTCUSDT"