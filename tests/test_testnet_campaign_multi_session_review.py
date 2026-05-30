from testnet_campaign.campaign_models import LongTestnetCampaignConfig
from testnet_campaign.campaign_runner import run_campaign_sessions
from testnet_campaign.multi_session_review import review_multi_session_campaign
from testnet_campaign.session_plans import build_default_campaign_session_plans


def force_safe_env(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_MODE", "testnet")
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")
    monkeypatch.setenv("TESTNET_ORDER_LIFECYCLE_MAX_NOTIONAL_USD", "100")


def test_multi_session_review_simulated_approves_real_campaign(monkeypatch):
    force_safe_env(monkeypatch)

    config = LongTestnetCampaignConfig(
        simulate=True,
        durations_minutes=[30, 120, 360, 720],
    )
    plans = build_default_campaign_session_plans(config=config)
    results = run_campaign_sessions(plans=plans, config=config)

    review = review_multi_session_campaign(
        sessions=results,
        config=config,
    )

    assert review.passed is True
    assert review.simulated is True
    assert review.decision == "APPROVED_FOR_REAL_TESTNET_CAMPAIGN"
    assert review.passed_sessions_count == 4


def test_multi_session_review_blocks_missing_required_session(monkeypatch):
    force_safe_env(monkeypatch)

    config = LongTestnetCampaignConfig(
        simulate=True,
        durations_minutes=[30],
    )
    plans = build_default_campaign_session_plans(config=config)
    results = run_campaign_sessions(plans=plans, config=config)

    review = review_multi_session_campaign(
        sessions=results,
        config=config,
    )

    assert review.passed is False
    assert "required_session_missing_120min" in review.blockers