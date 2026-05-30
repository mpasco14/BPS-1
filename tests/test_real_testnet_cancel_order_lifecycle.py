from testnet_order_lifecycle.cancel_order import cancel_real_testnet_order
from testnet_order_lifecycle.lifecycle_models import TestnetOrderLifecycleConfig


def test_cancel_order_simulated_allowed_passes():
    report = cancel_real_testnet_order(
        client_order_id="unit_order",
        config=TestnetOrderLifecycleConfig(
            simulate=True,
            allow_real_cancel=True,
        ),
    )

    assert report.passed is True
    assert report.canceled is True


def test_cancel_order_simulated_blocks_when_not_allowed():
    report = cancel_real_testnet_order(
        client_order_id="unit_order",
        config=TestnetOrderLifecycleConfig(
            simulate=True,
            allow_real_cancel=False,
        ),
    )

    assert report.passed is False
    assert "testnet_cancel_orders_not_allowed" in report.blockers