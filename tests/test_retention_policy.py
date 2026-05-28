import os
from datetime import datetime, timedelta, timezone

from data_persistence.retention_policy import (
    RetentionPolicyConfig,
    evaluate_retention_policy,
)


def test_retention_policy_marks_old_file_for_delete(tmp_path):
    old_file = tmp_path / "old.json"
    old_file.write_text("{}", encoding="utf-8")

    old_time = (datetime.now(timezone.utc) - timedelta(days=40)).timestamp()
    os.utime(old_file, (old_time, old_time))

    report = evaluate_retention_policy(
        root=tmp_path,
        config=RetentionPolicyConfig(dry_run=True, max_age_days=30, protected_dirs=[]),
    )

    assert report.passed is True
    assert report.delete_candidates_count == 1
    assert report.deleted_count == 0


def test_retention_policy_deletes_old_file_when_not_dry_run(tmp_path):
    old_file = tmp_path / "old.json"
    old_file.write_text("{}", encoding="utf-8")

    old_time = (datetime.now(timezone.utc) - timedelta(days=40)).timestamp()
    os.utime(old_file, (old_time, old_time))

    report = evaluate_retention_policy(
        root=tmp_path,
        config=RetentionPolicyConfig(dry_run=False, max_age_days=30, protected_dirs=[]),
    )

    assert report.passed is True
    assert report.delete_candidates_count == 1
    assert report.deleted_count == 1
    assert old_file.exists() is False


def test_retention_policy_keeps_protected_file(tmp_path):
    protected_dir = tmp_path / "security"
    protected_dir.mkdir()
    old_file = protected_dir / "audit.json"
    old_file.write_text("{}", encoding="utf-8")

    old_time = (datetime.now(timezone.utc) - timedelta(days=40)).timestamp()
    os.utime(old_file, (old_time, old_time))

    report = evaluate_retention_policy(
        root=tmp_path,
        config=RetentionPolicyConfig(
            dry_run=False,
            max_age_days=30,
            protected_dirs=[str(protected_dir)],
        ),
    )

    assert report.protected_count == 1
    assert report.deleted_count == 0
    assert old_file.exists() is True