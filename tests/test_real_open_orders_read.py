from binance_testnet_adapter.signed_client import BinanceSignedResponse, BinanceTestnetAdapterConfig, BinanceTestnetSignedClient
from testnet_readonly.open_orders_read import read_real_testnet_open_orders


class FakeOpenOrdersClient(BinanceTestnetSignedClient):
    def __init__(self, payload):
        super().__init__(config=BinanceTestnetAdapterConfig(simulate=True))
        self.payload = payload

    def request(self, **kwargs):
        return BinanceSignedResponse(
            status="SIMULATED",
            ok=True,
            method=kwargs.get("method", "GET"),
            path=kwargs.get("path", "/fapi/v1/openOrders"),
            data=self.payload,
            simulated=True,
        )


from binance_testnet_adapter.signed_client import BinanceTestnetAdapterConfig
from testnet_readonly.open_orders_read import read_real_testnet_open_orders


def test_real_open_orders_read_empty_passes():
    report = read_real_testnet_open_orders(
        symbol="BTCUSDT",
        adapter_config=BinanceTestnetAdapterConfig(
            simulate=True,
            allow_order_submission=False,
            allow_cancel_orders=False,
        ),
    )

    assert report.passed is True
    assert report.simulated is True
    assert report.open_orders_count == 0

def test_real_open_orders_read_blocks_when_orders_present():
    client = FakeOpenOrdersClient(
        payload=[
            {
                "symbol": "BTCUSDT",
                "orderId": 1,
                "clientOrderId": "unit",
                "side": "BUY",
                "type": "LIMIT",
                "status": "NEW",
                "price": "60000",
                "origQty": "0.001",
                "executedQty": "0",
                "reduceOnly": False,
            }
        ]
    )

    report = read_real_testnet_open_orders(
        symbol="BTCUSDT",
        client=client,
        allow_open_orders=False,
    )

    assert report.passed is False
    assert report.open_orders_count == 1
    assert "open_orders_detected_during_readonly_validation" in report.blockers


def test_real_open_orders_read_allows_when_configured():
    client = FakeOpenOrdersClient(
        payload=[
            {
                "symbol": "BTCUSDT",
                "orderId": 1,
                "clientOrderId": "unit",
                "side": "BUY",
                "type": "LIMIT",
                "status": "NEW",
                "price": "60000",
                "origQty": "0.001",
                "executedQty": "0",
                "reduceOnly": False,
            }
        ]
    )

    report = read_real_testnet_open_orders(
        symbol="BTCUSDT",
        client=client,
        allow_open_orders=True,
    )

    assert report.passed is True
    assert report.open_orders_count == 1
    assert "open_orders_present" in report.warnings