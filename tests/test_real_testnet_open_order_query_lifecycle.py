from testnet_order_lifecycle.lifecycle_models import TestnetOrderLifecycleConfig
from testnet_order_lifecycle.open_order_query import query_real_testnet_open_order


def test_open_order_query_simulated_passes():
    report = query_real_testnet_open_order(
        client_order_id="unit_order",
        config=TestnetOrderLifecycleConfig(simulate=True),
    )

    assert report.passed is True
    assert report.status == "OPEN_ORDER_FOUND"