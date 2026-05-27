from datetime import datetime, timedelta, timezone

from security.key_rotation_check import (
    KeyRotationConfig,
    KeyRotationRecord,
    build_key_rotation_check_report,
)


def test_key_rotation_passes_recent_key():
    now = datetime.now(timezone.utc)

    report = build_key_rotation_check_report(
        keys=[
            KeyRotationRecord(
                key_name="BINANCE_API_KEY",
                last_rotated_at=now - timedelta(days=5),
                next_rotation_due_at=now + timedelta(days=25),
                rotation_procedure_doc="docs/SECURITY.md",
            )
        ],
        config=KeyRotationConfig(max_age_days=30),
        now=now,
    )

    assert report.passed is True


def test_key_rotation_blocks_old_key():
    now = datetime.now(timezone.utc)

    report = build_key_rotation_check_report(
        keys=[
            KeyRotationRecord(
                key_name="BINANCE_API_KEY",
                last_rotated_at=now - timedelta(days=45),
                next_rotation_due_at=now + timedelta(days=1),
                rotation_procedure_doc="docs/SECURITY.md",
            )
        ],
        config=KeyRotationConfig(max_age_days=30),
        now=now,
    )

    assert report.passed is False
    assert "BINANCE_API_KEY:key_rotation_overdue" in report.blockers


def test_key_rotation_warns_missing_doc():
    now = datetime.now(timezone.utc)

    report = build_key_rotation_check_report(
        keys=[
            KeyRotationRecord(
                key_name="BINANCE_API_KEY",
                last_rotated_at=now - timedelta(days=5),
                next_rotation_due_at=now + timedelta(days=25),
            )
        ],
        now=now,
    )

    assert report.passed is True
    assert "BINANCE_API_KEY:rotation_procedure_doc_missing" in report.warnings