from datetime import datetime, timedelta, timezone

from ops.human_approval_workflow import (
    HumanApprovalConfig,
    HumanApprovalDecision,
    create_human_approval_request,
    validate_human_approval,
)


def test_human_approval_valid():
    config = HumanApprovalConfig(ttl_minutes=60)
    request = create_human_approval_request(
        approval_id="unit",
        requested_action="live_activation",
        reason="unit test",
        approver="Paulo",
        config=config,
    )

    report = validate_human_approval(
        request=request,
        decision=HumanApprovalDecision(
            approval_id="unit",
            approver="Paulo",
            approved=True,
            confirmation_phrase=config.required_phrase,
        ),
        config=config,
    )

    assert report.valid is True
    assert report.status == "APPROVED"


def test_human_approval_expired():
    config = HumanApprovalConfig(ttl_minutes=1)
    request = create_human_approval_request(
        approval_id="unit_expired",
        requested_action="live_activation",
        reason="unit test",
        approver="Paulo",
        config=config,
    )

    report = validate_human_approval(
        request=request,
        decision=HumanApprovalDecision(
            approval_id="unit_expired",
            approver="Paulo",
            approved=True,
            confirmation_phrase=config.required_phrase,
        ),
        config=config,
        now=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    assert report.valid is False
    assert "approval_expired" in report.blockers