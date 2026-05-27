from config_management.strategy_profiles import (
    StrategyParameterProfile,
    StrategyProfilesConfig,
    build_default_strategy_profiles,
    select_strategy_profile,
    validate_strategy_profile,
)


def test_strategy_profile_validation_passes_conservative():
    profile = select_strategy_profile(profiles=build_default_strategy_profiles(), name="conservative")
    report = validate_strategy_profile(profile=profile)

    assert report.passed is True


def test_strategy_profile_blocks_excessive_leverage():
    profile = StrategyParameterProfile(
        name="bad",
        max_leverage=100,
        max_margin_usd=5,
        risk_multiplier=0.5,
    )

    report = validate_strategy_profile(
        profile=profile,
        config=StrategyProfilesConfig(max_leverage=30),
    )

    assert report.passed is False
    assert "max_leverage_above_global_limit" in report.blockers


def test_select_strategy_profile():
    profile = select_strategy_profile(profiles=build_default_strategy_profiles(), name="balanced")

    assert profile.name == "balanced"