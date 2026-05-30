from micro_live.human_approval import HumanApprovalConfig, evaluate_human_approval


def test_human_approval_passes_exact_phrase():
    report = evaluate_human_approval(
        config=HumanApprovalConfig(
            operator_name="Paulo",
            approval_phrase="I APPROVE MICRO LIVE",
            approval_text="I APPROVE MICRO LIVE",
            require_human_approval=True,
        )
    )

    assert report.passed is True


def test_human_approval_blocks_missing_phrase():
    report = evaluate_human_approval(
        config=HumanApprovalConfig(
            operator_name="Paulo",
            approval_phrase="I APPROVE MICRO LIVE",
            approval_text="approved",
            require_human_approval=True,
        )
    )

    assert report.passed is False
    assert "human_approval_phrase_not_matched" in report.blockers