from binance_testnet_adapter.signed_client import BinanceTestnetAdapterConfig
from testnet_readonly.position_read import read_real_testnet_position_snapshot


def test_real_position_snapshot_read_simulated_flat_passes():
    report = read_real_testnet_position_snapshot(
        symbol="BTCUSDT",
        require_flat=True,
        adapter_config=BinanceTestnetAdapterConfig(
            simulate=True,
            allow_order_submission=False,
            allow_cancel_orders=False,
        ),
    )

    assert report.passed is True
    assert report.simulated is True
    assert report.flat is True
    assert report.symbol == "BTCUSDT"
