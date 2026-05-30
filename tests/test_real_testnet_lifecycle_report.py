from testnet_order_lifecycle.lifecycle_models import TestnetOrderLifecycleConfig
from testnet_order_lifecycle.lifecycle_report import build_real_testnet_lifecycle_report


def test_real_testnet_lifecycle_report_simulated_warn_or_passes(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_MODE", "testnet")
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")

    report = build_real_testnet_lifecycle_report(
        config=TestnetOrderLifecycleConfig(
            simulate=True,
            allow_real_submit=False,
            allow_real_cancel=True,
        )
    )

    assert report.passed is True
    assert report.simulated is True
    assert report.test_order_passed is True
    assert report.submit_passed is True
    assert report.final_flat is True