from release_private.release_models import PrivateReleaseConfig
from release_private.runbooks_review import review_final_runbooks


def test_runbooks_review_passes_existing_doc(tmp_path):
    doc = tmp_path / "RUNBOOK.md"
    doc.write_text("# Runbook\n", encoding="utf-8")

    report = review_final_runbooks(
        config=PrivateReleaseConfig(required_docs=[str(doc)], require_docs=True)
    )

    assert report.passed is True


def test_runbooks_review_blocks_missing_doc():
    report = review_final_runbooks(
        config=PrivateReleaseConfig(required_docs=["missing.md"], require_docs=True)
    )

    assert report.passed is False
    assert "required_runbook_missing:missing.md" in report.blockers