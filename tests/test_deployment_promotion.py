from release_management.deployment_promotion import (
    DeploymentPromotionInputs,
    evaluate_deployment_promotion,
)


def test_deployment_promotion_to_paper_passes():
    report = evaluate_deployment_promotion(
        inputs=DeploymentPromotionInputs(
            release_version="1.0.0",
            current_stage="dev",
            target_stage="paper",
            release_candidate_passed=True,
            quality_gate_passed=True,
            security_passed=True,
            infra_passed=True,
        )
    )

    assert report.approved is True
    assert report.action == "PROMOTE"


def test_deployment_promotion_to_micro_live_blocks_without_human_approval():
    report = evaluate_deployment_promotion(
        inputs=DeploymentPromotionInputs(
            release_version="1.0.0",
            current_stage="testnet",
            target_stage="micro_live",
            release_candidate_passed=True,
            quality_gate_passed=True,
            security_passed=True,
            infra_passed=True,
            paper_validated=True,
            testnet_validated=True,
            production_guard_passed=True,
            emergency_test_passed=True,
            human_approval_valid=False,
        )
    )

    assert report.approved is False
    assert "human_approval_not_valid" in report.blockers