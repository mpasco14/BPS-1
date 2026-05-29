from testnet_readonly.account_read import read_real_testnet_account_snapshot


def test_real_account_snapshot_read_simulated_passes():
    report = read_real_testnet_account_snapshot(symbol="BTCUSDT")

    assert report.passed is True
    assert report.simulated is True
    assert report.wallet_balance >= 0
    assert report.positions_count >= 1