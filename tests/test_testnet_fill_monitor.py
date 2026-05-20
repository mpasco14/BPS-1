from execution.binance_testnet_orders import BinanceTestnetOrderResult
from execution.testnet_fill_monitor import (
    TestnetFillMonitorConfig,
    monitor_order_until_terminal,
    parse_order_trade_update,
)


class FakeClient:
    def __init__(self):
        self.calls = 0

    def query_order(self, **kwargs):
        self.calls += 1
        status = "NEW" if self.calls == 1 else "FILLED"

        return BinanceTestnetOrderResult(
            action="QUERY",
            status="QUERIED",
            symbol="BTCUSDT",
            order_id=1,
            client_order_id="client-1",
            order_status=status,
            dry_run=False,
            response={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "origQty": "0.001",
                "price": "10000",
                "avgPrice": "10001",
                "status": status,
                "orderId": 1,
                "clientOrderId": "client-1",
            },
        )


def test_parse_order_trade_update():
    event = parse_order_trade_update(
        {
            "e": "ORDER_TRADE_UPDATE",
            "o": {
                "s": "BTCUSDT",
                "S": "BUY",
                "o": "LIMIT",
                "q": "0.001",
                "p": "10000",
                "X": "FILLED",
                "i": 1,
                "c": "client-1",
                "ap": "10001",
            },
        },
        session_name="unit",
    )

    assert event.status == "FILLED"
    assert event.symbol == "BTCUSDT"


def test_monitor_order_until_terminal():
    report = monitor_order_until_terminal(
        client=FakeClient(),
        symbol="BTCUSDT",
        order_id=1,
        session_name="unit",
        config=TestnetFillMonitorConfig(max_polls=3, poll_interval_seconds=0),
    )

    assert report.terminal is True
    assert report.final_status == "FILLED"
    assert report.polls == 2