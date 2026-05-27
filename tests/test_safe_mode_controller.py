from live_ops.safe_mode_controller import SafeModeRequest, SafeModeState, evaluate_safe_mode_request


def test_safe_mode_enter_approved():
    decision = evaluate_safe_mode_request(
        request=SafeModeRequest(
            action="ENTER_SAFE_MODE",
            reason="unit test",
        )
    )

    assert decision.approved is True
    assert decision.status_after == "ACTIVE"


def test_safe_mode_exit_requires_approval():
    decision = evaluate_safe_mode_request(
        state=SafeModeState(status="ACTIVE"),
        request=SafeModeRequest(
            action="EXIT_SAFE_MODE",
            reason="unit test",
            human_approval_valid=False,
        ),
    )

    assert decision.approved is False
    assert "human_approval_required_to_exit_safe_mode" in decision.blockers


def test_safe_mode_exit_with_approval():
    decision = evaluate_safe_mode_request(
        state=SafeModeState(status="ACTIVE"),
        request=SafeModeRequest(
            action="EXIT_SAFE_MODE",
            reason="unit test",
            human_approval_valid=True,
            approved_by="Paulo",
        ),
    )

    assert decision.approved is True
    assert decision.status_after == "INACTIVE"