from datetime import datetime, timezone

from ops.secrets_key_rotation_audit import (
    SecretKeyRecord,
    SecretsAuditConfig,
    build_secrets_key_rotation_audit_report,
)


def test_secrets_audit_passes_clean_records():
    report = build_secrets_key_rotation_audit_report(
        secrets=[
            SecretKeyRecord(
                name="BINANCE_API_KEY",
                present=True,
                storage_backend="vault",
                last_rotated_at=datetime.now(timezone.utc),
                permissions=["read", "trade"],
            )
        ],
        config=SecretsAuditConfig(warn_on_env_storage=False),
    )

    assert report.passed is True


def test_secrets_audit_blocks_withdraw_permission():
    report = build_secrets_key_rotation_audit_report(
        secrets=[
            SecretKeyRecord(
                name="BINANCE_API_KEY",
                present=True,
                storage_backend="vault",
                last_rotated_at=datetime.now(timezone.utc),
                permissions=["read", "trade", "withdraw"],
            )
        ],
        config=SecretsAuditConfig(),
    )

    assert report.passed is False
    assert "secret_has_forbidden_permission" in report.blockers