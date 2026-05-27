from release_management.changelog_generator import CommitRecord, build_changelog_report, classify_commit_message


def test_classify_commit_message():
    assert classify_commit_message("feat: add x") == "feature"
    assert classify_commit_message("fix: repair x") == "fix"
    assert classify_commit_message("security: harden x") == "security"


def test_build_changelog_report():
    report = build_changelog_report(
        version="1.0.0",
        commits=[
            CommitRecord(sha="abc123", message="feat: add release flow"),
            CommitRecord(sha="def456", message="fix: patch bug"),
        ],
    )

    assert report.entries_count == 2
    assert "# Changelog — 1.0.0" in report.markdown
    assert "Features" in report.markdown
    assert "Fixes" in report.markdown