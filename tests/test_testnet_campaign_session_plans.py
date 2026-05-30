from testnet_campaign.campaign_models import LongTestnetCampaignConfig
from testnet_campaign.session_plans import build_default_campaign_session_plans, session_label


def test_campaign_session_labels():
    assert session_label(30) == "30min"
    assert session_label(120) == "2h"
    assert session_label(360) == "6h"
    assert session_label(720) == "12h"


def test_default_campaign_session_plans_create_required_durations():
    plans = build_default_campaign_session_plans(
        config=LongTestnetCampaignConfig(
            durations_minutes=[30, 120, 360, 720],
            simulate=True,
        )
    )

    assert [item.duration_minutes for item in plans] == [30, 120, 360, 720]
    assert all(item.simulate is True for item in plans)