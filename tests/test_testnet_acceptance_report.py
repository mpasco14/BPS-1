from testnet_readiness.testnet_acceptance_report import build_testnet_acceptance_report
from testnet_readiness.testnet_fill_monitoring import build_demo_fill_events, monitor_testnet_fills_and_rejections
from testnet_readiness.testnet_order_lifecycle import build_demo_lifecycle_events, validate_testnet_order_lifecycle
from testnet_readiness.testnet_portfolio_reconciliation import build_flat_position, reconcile_testnet_portfolio
from testnet_readiness.testnet_reconciliation_engine import run_testnet_reconciliation_engine
from testnet_readiness.testnet_session_plan import build_testnet_session_plan, evaluate_testnet_session_plan


def test_testnet_acceptance_report_accepts_demo():
    plan = evaluate_testnet_session_plan(
        plan=build_testnet_session_plan(
            e2e_passed=True,
            scenario_testing_passed=True,
            kill_switch_test_passed=True,
        )
    )
    lifecycle = validate_testnet_order_lifecycle(events=build_demo_lifecycle_events())
    fill = monitor_testnet_fills_and_rejections(events=build_demo_fill_events())
    portfolio = reconcile_testnet_portfolio(
        local_position=build_flat_position(),
        exchange_position=build_flat_position(),
    )
    engine = run_testnet_reconciliation_engine(
        lifecycle=lifecycle,
        fill_monitor=fill,
        portfolio_reconciliation=portfolio,
    )

    report = build_testnet_acceptance_report(
        plan=plan,
        lifecycle=lifecycle,
        fill_monitor=fill,
        portfolio_reconciliation=portfolio,
        reconciliation_engine=engine,
    )

    assert report.accepted is True
    assert report.status in {"ACCEPTED", "WARN"}