from testnet_order_lifecycle.lifecycle_models import TestnetOrderLifecycleConfig
from testnet_order_lifecycle.small_limit_order_submit import submit_real_testnet_small_limit_order


def test_small_limit_order_submit_simulated_dry_run_passes(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_MODE", "testnet")
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")

    report = submit_real_testnet_small_limit_order(
        config=TestnetOrderLifecycleConfig(simulate=True),
    )

    assert report.passed is True
    assert report.status == "DRY_RUN"
    assert report.submitted is False


def test_small_limit_order_submit_blocks_notional_above_limit(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_MODE", "testnet")
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")

    report = submit_real_testnet_small_limit_order(
        config=TestnetOrderLifecycleConfig(
            simulate=True,
            quantity=1,
            price=60000,
            max_notional_usd=25,
        ),
    )

    assert report.passed is False
    assert "notional_above_lifecycle_limit" in report.blockers