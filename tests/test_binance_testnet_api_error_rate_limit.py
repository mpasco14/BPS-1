from binance_testnet_adapter.api_error import classify_binance_api_error


def test_binance_api_error_classifies_rate_limit():
    report = classify_binance_api_error(
        http_status=429,
        error_code=-1003,
        message="Too many requests.",
    )

    assert report.category == "RATE_LIMIT"
    assert report.retryable is True
    assert report.should_backoff is True


def test_binance_api_error_classifies_timestamp():
    report = classify_binance_api_error(
        error_code=-1021,
        message="Timestamp for this request is outside of the recvWindow.",
    )

    assert report.category == "TIMESTAMP"
    assert report.retryable is True


def test_binance_api_error_classifies_signature():
    report = classify_binance_api_error(
        error_code=-1022,
        message="Signature for this request is not valid.",
    )

    assert report.category == "SIGNATURE"
    assert report.retryable is False