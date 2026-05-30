from micro_live.credential_isolation import LiveCredentialIsolationConfig, evaluate_live_credential_isolation


def force_safe_env(monkeypatch):
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")


def test_credential_isolation_passes_without_required_keys(monkeypatch):
    force_safe_env(monkeypatch)

    report = evaluate_live_credential_isolation(
        config=LiveCredentialIsolationConfig(
            require_live_keys=False,
            live_api_key="",
            live_api_secret="",
            testnet_api_key="testnet_key",
            testnet_api_secret="testnet_secret",
        )
    )

    assert report.passed is True
    assert report.status == "WARN"


def test_credential_isolation_blocks_reused_keys(monkeypatch):
    force_safe_env(monkeypatch)

    report = evaluate_live_credential_isolation(
        config=LiveCredentialIsolationConfig(
            require_live_keys=True,
            live_api_key="same",
            live_api_secret="same_secret",
            testnet_api_key="same",
            testnet_api_secret="same_secret",
        )
    )

    assert report.passed is False
    assert "live_and_testnet_keys_not_isolated" in report.blockers