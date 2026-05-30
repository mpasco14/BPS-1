from binance_testnet_adapter.signed_client import BinanceTestnetAdapterConfig
from testnet_readonly.account_read import read_real_testnet_account_snapshot


def test_real_account_snapshot_read_simulated_passes():
    report = read_real_testnet_account_snapshot(
        symbol="BTCUSDT",
        adapter_config=BinanceTestnetAdapterConfig(
            simulate=True,
            allow_order_submission=False,
            allow_cancel_orders=False,
        ),
    )

    assert report.passed is True
    assert report.simulated is True
    assert report.symbol == "BTCUSDT"
