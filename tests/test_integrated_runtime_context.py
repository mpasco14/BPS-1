from system_integration.runtime_context import build_integrated_runtime_context, runtime_context_is_live_intent


def test_runtime_context_defaults_to_safe_mode():
    context = build_integrated_runtime_context(environment="development", execution_mode="paper")

    assert context.environment == "development"
    assert context.execution_mode == "paper"
    assert context.live_order_adapter_dry_run is True


def test_runtime_context_detects_live_intent():
    context = build_integrated_runtime_context(environment="live", execution_mode="live")

    assert runtime_context_is_live_intent(context) is True