from infra.runtime_config_validator import (
    RuntimeConfigInputs,
    RuntimeConfigValidatorConfig,
    validate_runtime_config,
)


def test_runtime_config_passes_safe_paper_defaults():
    report = validate_runtime_config(
        inputs=RuntimeConfigInputs(
            environment="development",
            execution_mode="paper",
            debug=False,
            binance_allow_live_trading=False,
            risk_allow_live_trading=False,
            live_order_adapter_enabled=False,
            live_order_adapter_dry_run=True,
            live_order_adapter_allow_submission=False,
            production_guard_enabled=True,
            kill_switch_enabled=True,
        ),
        config=RuntimeConfigValidatorConfig(),
    )

    assert report.passed is True


def test_runtime_config_blocks_live_when_not_allowed():
    report = validate_runtime_config(
        inputs=RuntimeConfigInputs(
            environment="production",
            execution_mode="live",
            binance_allow_live_trading=True,
            risk_allow_live_trading=True,
            live_order_adapter_enabled=True,
            live_order_adapter_dry_run=False,
            live_order_adapter_allow_submission=True,
            production_guard_enabled=True,
            kill_switch_enabled=True,
        ),
        config=RuntimeConfigValidatorConfig(allow_live=False),
    )

    assert report.passed is False
    assert "LIVE_NOT_ALLOWED_BY_RUNTIME_CONFIG_FAILED" in report.blockers