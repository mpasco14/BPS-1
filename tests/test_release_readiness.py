from quality.release_readiness import (
    ReleaseReadinessConfig,
    ReleaseReadinessInputs,
    evaluate_release_readiness,
)


def test_release_readiness_ready():
    report = evaluate_release_readiness(
        inputs=ReleaseReadinessInputs(
            version="v1.0.0",
            ci_passed=True,
            security_passed=True,
            infra_passed=True,
            docs_present=True,
            git_clean=True,
            warnings_count=0,
        ),
        config=ReleaseReadinessConfig(),
    )

    assert report.ready is True
    assert report.status == "READY"


def test_release_readiness_blocks_ci_failure():
    report = evaluate_release_readiness(
        inputs=ReleaseReadinessInputs(
            version="v1.0.0",
            ci_passed=False,
            security_passed=True,
            infra_passed=True,
            docs_present=True,
            git_clean=True,
        ),
        config=ReleaseReadinessConfig(),
    )

    assert report.ready is False
    assert "ci_not_passed" in report.blockers


def test_release_readiness_warns_on_quality_warnings():
    report = evaluate_release_readiness(
        inputs=ReleaseReadinessInputs(
            version="v1.0.0",
            ci_passed=True,
            security_passed=True,
            infra_passed=True,
            docs_present=True,
            git_clean=True,
            warnings_count=2,
        ),
        config=ReleaseReadinessConfig(),
    )

    assert report.ready is True
    assert report.status == "WARN"
    assert "quality_gate_has_warnings" in report.warnings