from testnet_supervision.credential_readiness import (
    TestnetCredentialReadinessConfig,
    evaluate_testnet_credential_readiness,
)


def test_testnet_credential_readiness_passes_without_required_keys():
    report = evaluate_testnet_credential_readiness(
        config=TestnetCredentialReadinessConfig(require_api_keys=False)
    )

    assert report.passed is True
    assert report.testnet_endpoint_detected is True


def test_testnet_credential_readiness_blocks_live_endpoint():
    report = evaluate_testnet_credential_readiness(
        config=TestnetCredentialReadinessConfig(
            rest_base_url="https://fapi.binance.com",
            ws_base_url="wss://fstream.binance.com",
            require_api_keys=False,
            require_testnet_endpoint=True,
        )
    )

    assert report.passed is False
    assert "testnet_endpoint_not_detected" in report.blockers