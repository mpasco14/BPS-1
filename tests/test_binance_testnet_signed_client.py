from binance_testnet_adapter.signed_client import (
    BinanceTestnetAdapterConfig,
    BinanceTestnetSignedClient,
    build_query_string,
    endpoint_is_testnet,
    sign_query_string,
)


def test_endpoint_is_testnet():
    assert endpoint_is_testnet("https://demo-fapi.binance.com") is True
    assert endpoint_is_testnet("https://fapi.binance.com") is False


def test_sign_query_string_is_stable():
    signature = sign_query_string("symbol=BTCUSDT&timestamp=1", "secret")

    assert len(signature) == 64


def test_signed_client_blocks_live_endpoint():
    client = BinanceTestnetSignedClient(
        config=BinanceTestnetAdapterConfig(
            rest_base_url="https://fapi.binance.com",
            api_key="key",
            api_secret="secret",
            simulate=False,
            require_testnet_endpoint=True,
        )
    )

    response = client.request(
        method="GET",
        path="/fapi/v3/account",
        params={},
        signed=True,
    )

    assert response.ok is False
    assert response.status == "BLOCKED"
    assert response.blocked_reason == "non_testnet_endpoint_blocked"


def test_signed_client_simulated_response():
    client = BinanceTestnetSignedClient(
        config=BinanceTestnetAdapterConfig(simulate=True)
    )

    response = client.request(
        method="GET",
        path="/fapi/v3/account",
        simulate_data={"ok": True},
    )

    assert response.ok is True
    assert response.simulated is True
    assert response.data["ok"] is True