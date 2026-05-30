from micro_live.api_permission_audit import LiveAPIPermissionAuditConfig, audit_live_api_permissions


def test_permission_audit_passes_minimal_trade_permissions():
    report = audit_live_api_permissions(
        config=LiveAPIPermissionAuditConfig(
            futures_trading_permission=True,
            withdrawals_permission=False,
            universal_transfer_permission=False,
            ip_restricted=True,
            read_only=False,
        )
    )

    assert report.passed is True


def test_permission_audit_blocks_withdrawals():
    report = audit_live_api_permissions(
        config=LiveAPIPermissionAuditConfig(
            futures_trading_permission=True,
            withdrawals_permission=True,
            universal_transfer_permission=False,
            ip_restricted=True,
            read_only=False,
        )
    )

    assert report.passed is False
    assert "withdrawals_permission_must_be_disabled" in report.blockers