from live_ops.operator_command_console import OperatorCommandRequest, evaluate_operator_command


def test_operator_command_status_allowed():
    decision = evaluate_operator_command(
        request=OperatorCommandRequest(
            command_id="status",
            command="STATUS",
        )
    )

    assert decision.approved is True
    assert decision.target == "console"


def test_operator_command_protected_requires_approval():
    decision = evaluate_operator_command(
        request=OperatorCommandRequest(
            command_id="resume",
            command="RESUME_TRADING",
            reason="unit test",
            human_approval_valid=False,
        )
    )

    assert decision.approved is False
    assert "human_approval_required_for_protected_command" in decision.blockers


def test_operator_command_kill_switch_allowed_without_reason():
    decision = evaluate_operator_command(
        request=OperatorCommandRequest(
            command_id="kill",
            command="ACTIVATE_KILL_SWITCH",
        )
    )

    assert decision.approved is True
    assert decision.target == "kill_switch"