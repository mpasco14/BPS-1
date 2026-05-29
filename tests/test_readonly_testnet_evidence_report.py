from testnet_readonly.readonly_evidence_report import (
    ReadOnlyTestnetEvidenceConfig,
    run_readonly_testnet_validation,
)


def force_safe_readonly_env(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_MODE", "testnet")
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")

    monkeypatch.setenv("BINANCE_TESTNET_REST_BASE_URL", "https://demo-fapi.binance.com")
    monkeypatch.setenv("BINANCE_TESTNET_SIMULATE", "true")
    monkeypatch.setenv("BINANCE_TESTNET_REQUIRE_TESTNET_ENDPOINT", "true")
    monkeypatch.setenv("BINANCE_TESTNET_ALLOW_ORDER_SUBMISSION", "false")
    monkeypatch.setenv("BINANCE_TESTNET_ALLOW_CANCEL_ORDERS", "false")

    monkeypatch.setenv("TESTNET_READONLY_REQUIRE_REAL_MODE", "false")
    monkeypatch.setenv("TESTNET_READONLY_REQUIRE_NO_LIVE_FLAGS", "true")
    monkeypatch.setenv("TESTNET_READONLY_REQUIRE_FINAL_FLAT", "true")
    monkeypatch.setenv("TESTNET_READONLY_ALLOW_OPEN_ORDERS", "false")


def test_readonly_testnet_evidence_report_simulated_warn_passes(monkeypatch):
    force_safe_readonly_env(monkeypatch)

    report = run_readonly_testnet_validation(
        symbol="BTCUSDT",
        config=ReadOnlyTestnetEvidenceConfig(
            symbol="BTCUSDT",
            require_real_mode=False,
            require_no_live_flags=True,
            require_final_flat=True,
            allow_open_orders=False,
        ),
    )

    assert report.passed is True
    assert report.status == "WARN"
    assert report.simulated is True
    assert report.final_flat is True
    assert report.open_orders_count == 0
    assert report.blockers == []