from binance_testnet_adapter.signed_client import BinanceTestnetAdapterConfig
from testnet_readonly.credential_check import (
    RealTestnetCredentialCheckConfig,
    evaluate_real_testnet_credential_check,
)


def force_safe_readonly_env(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_MODE", "testnet")
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")
    monkeypatch.setenv("BINANCE_TESTNET_ALLOW_ORDER_SUBMISSION", "false")
    monkeypatch.setenv("BINANCE_TESTNET_ALLOW_CANCEL_ORDERS", "false")
    monkeypatch.setenv("BINANCE_TESTNET_SIMULATE", "true")
    monkeypatch.setenv("TESTNET_READONLY_REQUIRE_REAL_MODE", "false")
    monkeypatch.setenv("TESTNET_READONLY_REQUIRE_NO_LIVE_FLAGS", "true")


def test_real_testnet_credential_check_simulated_warn_passes(monkeypatch):
    force_safe_readonly_env(monkeypatch)

    report = evaluate_real_testnet_credential_check(
        adapter_config=BinanceTestnetAdapterConfig(
            rest_base_url="https://demo-fapi.binance.com",
            simulate=True,
            allow_order_submission=False,
            allow_cancel_orders=False,
        ),
        config=RealTestnetCredentialCheckConfig(
            require_real_mode=False,
            require_no_live_flags=True,
        ),
    )

    assert report.passed is True
    assert report.status == "WARN"
    assert "adapter_is_simulated" in report.warnings


def test_real_testnet_credential_check_blocks_live_endpoint(monkeypatch):
    force_safe_readonly_env(monkeypatch)

    report = evaluate_real_testnet_credential_check(
        adapter_config=BinanceTestnetAdapterConfig(
            rest_base_url="https://fapi.binance.com",
            simulate=True,
            allow_order_submission=False,
            allow_cancel_orders=False,
        ),
        config=RealTestnetCredentialCheckConfig(
            require_real_mode=False,
            require_no_live_flags=True,
        ),
    )

    assert report.passed is False
    assert "testnet_endpoint_not_detected" in report.blockers


def test_real_testnet_credential_check_blocks_order_submission(monkeypatch):
    force_safe_readonly_env(monkeypatch)

    report = evaluate_real_testnet_credential_check(
        adapter_config=BinanceTestnetAdapterConfig(
            rest_base_url="https://demo-fapi.binance.com",
            simulate=True,
            allow_order_submission=True,
            allow_cancel_orders=False,
        ),
        config=RealTestnetCredentialCheckConfig(
            require_real_mode=False,
            require_no_live_flags=True,
        ),
    )

    assert report.passed is False
    assert "order_submission_must_be_disabled_for_readonly_validation" in report.blockers