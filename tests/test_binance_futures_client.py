from execution.binance_futures_client import (
    BinanceFuturesConfig,
    build_signed_params,
    mask_secret,
    sign_query,
)


def test_mask_secret():
    assert mask_secret("abcdef") == "abcd**"
    assert mask_secret("") == ""


def test_sign_query_returns_sha256_hex():
    signature = sign_query(
        {"symbol": "BTCUSDT", "timestamp": 1},
        "secret",
    )

    assert len(signature) == 64


def test_build_signed_params():
    params = build_signed_params(
        {"symbol": "BTCUSDT"},
        secret="secret",
        timestamp=1,
        recv_window=5000,
    )

    assert params["symbol"] == "BTCUSDT"
    assert params["timestamp"] == 1
    assert params["recvWindow"] == 5000
    assert "signature" in params


def test_config_base_url_testnet():
    config = BinanceFuturesConfig(
        execution_mode="testnet",
        testnet_rest_base_url="https://demo-fapi.binance.com",
    )

    assert config.active_base_url == "https://demo-fapi.binance.com"


def test_config_base_url_live_or_paper():
    config = BinanceFuturesConfig(
        execution_mode="paper",
        rest_base_url="https://fapi.binance.com",
    )

    assert config.active_base_url == "https://fapi.binance.com"