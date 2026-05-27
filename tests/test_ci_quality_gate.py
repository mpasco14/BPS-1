from quality.ci_quality_gate import QualityCheck, evaluate_quality_gate


def test_quality_gate_passes_all_checks():
    report = evaluate_quality_gate(
        checks=[
            QualityCheck(
                check_id="unit_1",
                name="Unit check",
                status="PASS",
            ),
            QualityCheck(
                check_id="unit_2",
                name="Unit check 2",
                status="PASS",
            ),
        ]
    )

    assert report.passed is True
    assert report.status == "PASS"


def test_quality_gate_blocks_failed_blocking_check():
    report = evaluate_quality_gate(
        checks=[
            QualityCheck(
                check_id="pytest",
                name="Tests",
                status="FAIL",
                severity="CRITICAL",
                blocking=True,
            )
        ]
    )

    assert report.passed is False
    assert report.status == "FAIL"
    assert "pytest" in report.blockers


def test_quality_gate_warns_non_blocking_failure():
    report = evaluate_quality_gate(
        checks=[
            QualityCheck(
                check_id="optional",
                name="Optional",
                status="FAIL",
                severity="LOW",
                blocking=False,
            )
        ]
    )

    assert report.passed is True
    assert report.status == "WARN"
    assert "optional" in report.warnings