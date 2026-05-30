from release_private.release_lock import ReleaseLockInputs, evaluate_release_lock
from release_private.release_models import PrivateReleaseConfig


def test_release_lock_passes_clean_synced_tests_passed():
    report = evaluate_release_lock(
        inputs=ReleaseLockInputs(
            branch="main",
            git_clean=True,
            upstream_synced=True,
            tests_passed=True,
            tag_exists=False,
        ),
        config=PrivateReleaseConfig(require_tests_passed=True),
    )

    assert report.passed is True


def test_release_lock_blocks_existing_tag():
    report = evaluate_release_lock(
        inputs=ReleaseLockInputs(
            branch="main",
            git_clean=True,
            upstream_synced=True,
            tests_passed=True,
            tag_exists=True,
        )
    )

    assert report.passed is False
    assert "release_tag_already_exists" in report.blockers