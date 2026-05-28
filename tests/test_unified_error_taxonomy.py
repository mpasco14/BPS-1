from system_integration.error_taxonomy import aggregate_system_blockers, build_system_blocker


def test_error_taxonomy_passes_empty_blockers():
    report = aggregate_system_blockers(blockers=[])

    assert report.passed is True
    assert report.status == "PASS"


def test_error_taxonomy_blocks_critical():
    report = aggregate_system_blockers(
        blockers=[
            build_system_blocker(
                code="RISK_BLOCK",
                severity="CRITICAL",
                source="unit",
                message="risk blocked",
            )
        ]
    )

    assert report.passed is False
    assert "RISK_BLOCK" in report.blocking_codes