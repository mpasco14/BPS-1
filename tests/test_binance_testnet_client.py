import pytest

from execution.binance_testnet_client import (
    BinanceTestnetConfig,
    assert_testnet_order_submission_allowed,
    evaluate_binance_testnet_readiness,
)


def test_testnet_readiness_fails_without_keys():
    report = evaluate_binance_testnet_readiness(
        BinanceTestnetConfig(
            enabled=True,
            api_key=None,
            api_secret=None,
        )
    )

    assert report.ready is False
    assert "testnet_api_key_missing" in report.blockers
    assert "testnet_api_secret_missing" in report.blockers


def test_testnet_readiness_passes_with_keys():
    report = evaluate_binance_testnet_readiness(
        BinanceTestnetConfig(
            enabled=True,
            api_key="key",
            api_secret="secret",
        )
    )

    assert report.ready is True


def test_testnet_order_submission_blocked_by_default():
    with pytest.raises(PermissionError):
        assert_testnet_order_submission_allowed(
            BinanceTestnetConfig(
                enabled=True,
                api_key="key",
                api_secret="secret",
                allow_order_submission=False,
            )
        )