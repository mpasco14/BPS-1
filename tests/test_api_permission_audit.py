from security.api_permission_audit import (
    ApiKeyPermissionRecord,
    ApiPermissionAuditConfig,
    build_api_permission_audit_report,
)


def test_api_permission_audit_passes_safe_key():
    report = build_api_permission_audit_report(
        keys=[
            ApiKeyPermissionRecord(
                key_name="binance_testnet",
                read_enabled=True,
                trade_enabled=True,
                futures_enabled=True,
                withdrawal_enabled=False,
                transfer_enabled=False,
            )
        ],
        config=ApiPermissionAuditConfig(require_ip_restriction=False),
    )

    assert report.passed is True


def test_api_permission_audit_blocks_withdrawal():
    report = build_api_permission_audit_report(
        keys=[
            ApiKeyPermissionRecord(
                key_name="bad_key",
                read_enabled=True,
                trade_enabled=True,
                futures_enabled=True,
                withdrawal_enabled=True,
            )
        ]
    )

    assert report.passed is False
    assert "bad_key:withdrawal_permission_enabled" in report.blockers


def test_api_permission_audit_blocks_missing_trade():
    report = build_api_permission_audit_report(
        keys=[
            ApiKeyPermissionRecord(
                key_name="read_only",
                read_enabled=True,
                trade_enabled=False,
                futures_enabled=True,
            )
        ]
    )

    assert report.passed is False
    assert "read_only:trade_permission_missing" in report.blockers