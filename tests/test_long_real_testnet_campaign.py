from testnet_campaign.campaign_models import CampaignIterationResult, LongTestnetCampaignConfig
from testnet_campaign.long_campaign_runner import build_campaign_report


def test_campaign_report_promotes_all_passed_iterations():
    config = LongTestnetCampaignConfig(
        campaign_name="unit_campaign",
        duration_minutes=30,
        interval_seconds=1,
        max_iterations=2,
    )

    iterations = [
        CampaignIterationResult(
            iteration=1,
            status="WARN",
            passed=True,
            simulated=False,
            submitted=True,
            cancel_passed=True,
            final_flat=True,
            rejection_detected=False,
            warnings=["test_order_validation_only_no_matching_engine_submission"],
        ),
        CampaignIterationResult(
            iteration=2,
            status="WARN",
            passed=True,
            simulated=False,
            submitted=True,
            cancel_passed=True,
            final_flat=True,
            rejection_detected=False,
            warnings=["test_order_validation_only_no_matching_engine_submission"],
        ),
    ]

    report = build_campaign_report(iterations=iterations, config=config)

    assert report.passed is True
    assert report.status == "WARN"
    assert report.decision == "HOLD"
    assert report.passed_iterations == 2
    assert report.final_flat_count == 2


def test_campaign_report_blocks_rejection():
    config = LongTestnetCampaignConfig(
        campaign_name="unit_campaign",
        duration_minutes=30,
        interval_seconds=1,
        max_iterations=1,
    )

    iterations = [
        CampaignIterationResult(
            iteration=1,
            status="FAIL",
            passed=False,
            simulated=False,
            submitted=True,
            cancel_passed=False,
            final_flat=False,
            rejection_detected=True,
            blockers=["rejection_detected"],
        )
    ]

    report = build_campaign_report(iterations=iterations, config=config)

    assert report.passed is False
    assert "rejection_detected" in report.blockers