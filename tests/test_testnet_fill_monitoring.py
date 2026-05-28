from testnet_readiness.testnet_fill_monitoring import (
    TestnetFillEvent,
    build_demo_fill_events,
    monitor_testnet_fills_and_rejections,
)


def test_testnet_fill_monitor_demo_passes():
    report = monitor_testnet_fills_and_rejections(events=build_demo_fill_events())

    assert report.passed is True
    assert report.fill_rate == 1.0


def test_testnet_fill_monitor_blocks_rejections():
    events = [
        TestnetFillEvent(event_id="r1", order_id="order_1", event_type="REJECTION", rejection_reason="unit"),
    ]

    report = monitor_testnet_fills_and_rejections(events=events)

    assert report.passed is False
    assert "fill_rate_below_minimum" in report.blockers
    assert "rejection_rate_above_limit" in report.blockers