from release_management.release_candidate_checklist import (
    ReleaseCandidateInputs,
    evaluate_release_candidate_checklist,
)


def test_release_candidate_passes_when_all_required_present():
    report = evaluate_release_candidate_checklist(
        inputs=ReleaseCandidateInputs(
            version="1.0.0",
            quality_gate_passed=True,
            tests_passed=True,
            security_passed=True,
            infra_passed=True,
            docs_present=True,
            changelog_present=True,
            version_manifest_present=True,
            model_pinned=True,
            config_pinned=True,
            deployment_plan_present=True,
            git_clean=True,
        )
    )

    assert report.passed is True


def test_release_candidate_blocks_missing_model_pin():
    report = evaluate_release_candidate_checklist(
        inputs=ReleaseCandidateInputs(
            version="1.0.0",
            quality_gate_passed=True,
            tests_passed=True,
            security_passed=True,
            infra_passed=True,
            docs_present=True,
            changelog_present=True,
            version_manifest_present=True,
            model_pinned=False,
            config_pinned=True,
            deployment_plan_present=True,
            git_clean=True,
        )
    )

    assert report.passed is False
    assert "model_not_pinned" in report.blockers