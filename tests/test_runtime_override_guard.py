from config_management.runtime_override_guard import (
    RuntimeOverrideRequest,
    evaluate_runtime_override,
)


def test_runtime_override_allows_safe_dev_change():
    decision = evaluate_runtime_override(
        request=RuntimeOverrideRequest(
            override_id="unit",
            key="strategy.min_confidence",
            old_value=0.65,
            new_value=0.62,
            environment="development",
            reason="unit test",
        )
    )

    assert decision.approved is True


def test_runtime_override_blocks_protected_key():
    decision = evaluate_runtime_override(
        request=RuntimeOverrideRequest(
            override_id="unit_protected",
            key="live_order_adapter_allow_submission",
            old_value=False,
            new_value=True,
            environment="development",
            reason="unit test",
        )
    )

    assert decision.approved is False
    assert "protected_key_override_blocked" in decision.blockers


def test_runtime_override_requires_human_approval_for_live():
    decision = evaluate_runtime_override(
        request=RuntimeOverrideRequest(
            override_id="unit_live",
            key="strategy.min_confidence",
            old_value=0.65,
            new_value=0.62,
            environment="production",
            reason="unit test",
            human_approval_valid=False,
        )
    )

    assert decision.approved is False
    assert "human_approval_required_for_live_override" in decision.blockers