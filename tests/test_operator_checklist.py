from v1_acceptance.operator_checklist import (
    build_v1_operator_checklist,
    evaluate_operator_checklist,
)


def test_operator_checklist_demo_passes():
    checklist = build_v1_operator_checklist(
        operator="Paulo",
        mark_demo_passed=True,
    )

    report = evaluate_operator_checklist(checklist=checklist)

    assert report.passed is True
    assert report.passed_items == report.total_items


def test_operator_checklist_blocks_pending_required_items():
    checklist = build_v1_operator_checklist(
        operator="Paulo",
        mark_demo_passed=False,
    )

    report = evaluate_operator_checklist(checklist=checklist)

    assert report.passed is False
    assert report.pending_items > 0