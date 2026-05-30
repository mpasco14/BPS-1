from testnet_campaign.campaign_models import LongTestnetCampaignConfig
from testnet_campaign.campaign_runner import run_campaign_session
from testnet_campaign.session_plans import build_campaign_session_plan


def force_safe_env(monkeypatch):
    monkeypatch.setenv("BINANCE_EXECUTION_MODE", "testnet")
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("RISK_ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", "false")
    monkeypatch.setenv("TESTNET_ORDER_LIFECYCLE_MAX_NOTIONAL_USD", "100")


def test_campaign_runner_30min_simulated_passes(monkeypatch):
    force_safe_env(monkeypatch)

    config = LongTestnetCampaignConfig(
        simulate=True,
        allow_real_submit=False,
        allow_real_cancel=False,
    )
    plan = build_campaign_session_plan(
        duration_minutes=30,
        session_name="unit_30min",
        config=config,
    )

    result = run_campaign_session(plan=plan, config=config)

    assert result.passed is True
    assert result.simulated is True
    assert result.duration_minutes == 30
    assert result.test_order_passed is True
    assert result.final_flat is True


def test_campaign_runner_blocks_live_flags(monkeypatch):
    force_safe_env(monkeypatch)
    monkeypatch.setenv("BINANCE_ALLOW_LIVE_TRADING", "true")

    config = LongTestnetCampaignConfig(
        simulate=True,
        require_no_live_flags=True,
    )
    plan = build_campaign_session_plan(
        duration_minutes=30,
        session_name="unit_block_live",
        config=config,
    )

    result = run_campaign_session(plan=plan, config=config)

    assert result.passed is False
    assert "live_flags_detected" in result.blockers