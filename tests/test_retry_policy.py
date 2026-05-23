from infra.retry_policy import (
    RetryContext,
    RetryPolicyConfig,
    calculate_backoff_delay,
    evaluate_retry_decision,
)


def test_retry_policy_retries_429():
    decision = evaluate_retry_decision(
        context=RetryContext(
            operation_name="binance_order",
            attempt=1,
            status_code=429,
        ),
        config=RetryPolicyConfig(max_attempts=3, base_delay_seconds=0.5, multiplier=2),
    )

    assert decision.should_retry is True
    assert decision.status == "RETRY"
    assert decision.delay_seconds == 0.5


def test_retry_policy_gives_up_at_max_attempts():
    decision = evaluate_retry_decision(
        context=RetryContext(
            operation_name="binance_order",
            attempt=3,
            status_code=429,
        ),
        config=RetryPolicyConfig(max_attempts=3),
    )

    assert decision.should_retry is False
    assert decision.status == "GIVE_UP"


def test_calculate_backoff_delay():
    delay = calculate_backoff_delay(
        attempt=3,
        config=RetryPolicyConfig(base_delay_seconds=0.5, multiplier=2, max_delay_seconds=10),
    )

    assert delay == 2.0