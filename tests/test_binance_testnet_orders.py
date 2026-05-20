from execution.binance_testnet_client import BinanceTestnetConfig
from execution.binance_testnet_orders import (
    BinanceTestnetOrderRequest,
    BinanceTestnetOrdersClient,
    build_order_params,
    build_signed_params,
)


def test_build_signed_params_adds_signature():
    params = build_signed_params(
        {"symbol": "BTCUSDT", "timestamp": 1},
        api_secret="secret",
    )

    assert "signature" in params


def test_build_order_params():
    request = BinanceTestnetOrderRequest(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.001",
        price="10000",
    )

    params = build_order_params(request)

    assert params["symbol"] == "BTCUSDT"
    assert params["side"] == "BUY"
    assert params["quantity"] == "0.001"


def test_create_order_dry_run():
    client = BinanceTestnetOrdersClient(
        BinanceTestnetConfig(
            enabled=True,
            api_key=None,
            api_secret=None,
        )
    )

    result = client.create_order(
        BinanceTestnetOrderRequest(
            symbol="BTCUSDT",
            side="BUY",
            quantity="0.001",
            price="10000",
        ),
        dry_run=True,
    )

    assert result.status == "DRY_RUN"
    assert result.dry_run is True