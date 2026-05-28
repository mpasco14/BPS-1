from binance_testnet_adapter.order_submit import (
    BinanceTestnetOrderSubmitRequest,
    submit_binance_testnet_order,
)
from binance_testnet_adapter.signed_client import BinanceTestnetAdapterConfig


def test_binance_testnet_order_submit_dry_run_passes():
    report = submit_binance_testnet_order(
        request=BinanceTestnetOrderSubmitRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=0.001,
            price=60000,
            dry_run=True,
        )
    )

    assert report.passed is True
    assert report.status == "DRY_RUN"
    assert report.submitted is False


def test_binance_testnet_order_submit_blocks_real_submission_by_default():
    report = submit_binance_testnet_order(
        request=BinanceTestnetOrderSubmitRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=0.001,
            price=60000,
            dry_run=False,
        ),
        config=BinanceTestnetAdapterConfig(
            simulate=True,
            allow_order_submission=False,
        ),
    )

    assert report.passed is False
    assert "testnet_order_submission_not_allowed" in report.blockers


def test_binance_testnet_order_submit_blocks_missing_limit_price():
    report = submit_binance_testnet_order(
        request=BinanceTestnetOrderSubmitRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=0.001,
            price=None,
            dry_run=True,
        )
    )

    assert report.passed is False
    assert "price_required_for_limit_order" in report.blockers