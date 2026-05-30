from release_private.evidence_pack import build_artifact_evidence_pack
from release_private.release_models import PrivateReleaseConfig


def test_evidence_pack_warns_missing_when_not_strict():
    report = build_artifact_evidence_pack(
        config=PrivateReleaseConfig(
            required_artifacts=["missing.json"],
            require_artifacts=False,
        )
    )

    assert report.passed is True
    assert "artifact_missing:missing.json" in report.warnings


def test_evidence_pack_blocks_missing_when_strict():
    report = build_artifact_evidence_pack(
        config=PrivateReleaseConfig(
            required_artifacts=["missing.json"],
            require_artifacts=True,
        )
    )

    assert report.passed is False
    assert "required_artifact_missing:missing.json" in report.blockers