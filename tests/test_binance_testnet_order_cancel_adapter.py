from binance_testnet_adapter.order_cancel import (
    BinanceTestnetCancelOrderRequest,
    cancel_binance_testnet_order,
    query_binance_testnet_open_order,
)
from binance_testnet_adapter.signed_client import BinanceTestnetAdapterConfig


def test_query_binance_testnet_open_order_simulated():
    report = query_binance_testnet_open_order(
        request=BinanceTestnetCancelOrderRequest(
            symbol="BTCUSDT",
            orig_client_order_id="unit_order",
        )
    )

    assert report.passed is True
    assert report.status == "OPEN_ORDER_FOUND"


def test_cancel_binance_testnet_order_blocks_by_default():
    report = cancel_binance_testnet_order(
        request=BinanceTestnetCancelOrderRequest(
            symbol="BTCUSDT",
            orig_client_order_id="unit_order",
        ),
        config=BinanceTestnetAdapterConfig(
            simulate=True,
            allow_cancel_orders=False,
        ),
    )

    assert report.passed is False
    assert "testnet_cancel_orders_not_allowed" in report.blockers


def test_cancel_binance_testnet_order_requires_identifier():
    report = cancel_binance_testnet_order(
        request=BinanceTestnetCancelOrderRequest(symbol="BTCUSDT")
    )

    assert report.passed is False
    assert "order_id_or_orig_client_order_id_required" in report.blockers