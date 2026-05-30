from testnet_order_lifecycle.lifecycle_models import TestnetOrderLifecycleConfig
from testnet_order_lifecycle.test_order_validation import validate_real_testnet_test_order


def test_real_testnet_test_order_validation_simulated_passes(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_MODE", "testnet")
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")

    report = validate_real_testnet_test_order(
        config=TestnetOrderLifecycleConfig(simulate=True)
    )

    assert report.passed is True
    assert report.status == "VALIDATED"
    assert report.submitted is False