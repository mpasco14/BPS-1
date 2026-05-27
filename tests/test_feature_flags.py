from config_management.feature_flags import FeatureFlag, FeatureFlagContext, evaluate_feature_flag, evaluate_feature_flags


def test_feature_flag_enabled_for_environment():
    decision = evaluate_feature_flag(
        flag=FeatureFlag(
            name="sentiment",
            enabled=True,
            environments=["development"],
            rollout_percentage=100,
        ),
        context=FeatureFlagContext(environment="development"),
    )

    assert decision.enabled is True


def test_feature_flag_disabled_wrong_environment():
    decision = evaluate_feature_flag(
        flag=FeatureFlag(
            name="live_feature",
            enabled=True,
            environments=["production"],
            rollout_percentage=100,
        ),
        context=FeatureFlagContext(environment="development"),
    )

    assert decision.enabled is False
    assert decision.reason == "environment_not_allowed"


def test_feature_flags_report_counts():
    report = evaluate_feature_flags(
        flags=[
            FeatureFlag(name="a", enabled=True, rollout_percentage=100),
            FeatureFlag(name="b", enabled=False),
        ],
        context=FeatureFlagContext(environment="development"),
    )

    assert report.flags_count == 2
    assert report.enabled_count == 1