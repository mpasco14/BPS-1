from testnet_readiness.testnet_fill_monitoring import build_demo_fill_events, monitor_testnet_fills_and_rejections
from testnet_readiness.testnet_order_lifecycle import build_demo_lifecycle_events, validate_testnet_order_lifecycle
from testnet_readiness.testnet_portfolio_reconciliation import build_flat_position, reconcile_testnet_portfolio
from testnet_readiness.testnet_reconciliation_engine import run_testnet_reconciliation_engine


def test_testnet_reconciliation_engine_passes_demo():
    lifecycle = validate_testnet_order_lifecycle(events=build_demo_lifecycle_events())
    fill = monitor_testnet_fills_and_rejections(events=build_demo_fill_events())
    portfolio = reconcile_testnet_portfolio(
        local_position=build_flat_position(),
        exchange_position=build_flat_position(),
    )

    report = run_testnet_reconciliation_engine(
        lifecycle=lifecycle,
        fill_monitor=fill,
        portfolio_reconciliation=portfolio,
    )

    assert report.passed is True