from ops.discipline_score import (
    DisciplinePolicyEvent,
    build_discipline_score_report,
    export_discipline_score_report,
)


def test_discipline_score_all_pass():
    report = build_discipline_score_report(
        events=[
            DisciplinePolicyEvent(event_id="1", pillar="risk", rule_code="risk_ok", passed=True),
            DisciplinePolicyEvent(event_id="2", pillar="execution", rule_code="exec_ok", passed=True),
        ]
    )

    assert report.passed is True
    assert report.discipline_score == 1.0


def test_discipline_score_blocks_critical_violation():
    report = build_discipline_score_report(
        events=[
            DisciplinePolicyEvent(
                event_id="1",
                pillar="risk",
                rule_code="risk_violation",
                passed=False,
                severity="CRITICAL",
            )
        ]
    )

    assert report.passed is False
    assert "risk_violation" in report.blockers


def test_export_discipline_score_report(tmp_path):
    report = build_discipline_score_report(events=[])

    path = export_discipline_score_report(
        report,
        output_dir=tmp_path,
        name="unit_discipline",
    )

    assert path.exists()