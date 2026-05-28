from testnet_readiness.testnet_order_lifecycle import (
    TestnetOrderLifecycleEvent,
    build_demo_lifecycle_events,
    validate_testnet_order_lifecycle,
)


def test_testnet_order_lifecycle_demo_passes():
    report = validate_testnet_order_lifecycle(events=build_demo_lifecycle_events())

    assert report.passed is True
    assert report.orders_count == 1
    assert report.filled_count == 1


def test_testnet_order_lifecycle_blocks_missing_ack():
    events = [
        TestnetOrderLifecycleEvent(event_id="e1", order_id="order_1", event_type="PLANNED"),
        TestnetOrderLifecycleEvent(event_id="e2", order_id="order_1", event_type="SUBMITTED"),
    ]

    report = validate_testnet_order_lifecycle(events=events)

    assert report.passed is False
    assert "order_1:acknowledged_event_missing" in report.blockers