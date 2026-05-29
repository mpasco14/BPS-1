from testnet_readonly.position_read import read_real_testnet_position_snapshot


def test_real_position_snapshot_read_simulated_flat_passes():
    report = read_real_testnet_position_snapshot(symbol="BTCUSDT", require_flat=True)

    assert report.passed is True
    assert report.simulated is True
    assert report.flat is True