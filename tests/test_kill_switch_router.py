from live_ops.kill_switch_router import KillSwitchRequest, KillSwitchState, route_kill_switch_command


def test_kill_switch_activation_executes_required_steps():
    report = route_kill_switch_command(
        request=KillSwitchRequest(
            command="ACTIVATE",
            reason="unit test",
        )
    )

    step_ids = {step["step_id"] for step in report.steps}

    assert report.approved is True
    assert report.active_after is True
    assert "block_new_orders" in step_ids
    assert "cancel_open_orders" in step_ids
    assert "enter_safe_mode" in step_ids


def test_kill_switch_reset_requires_approval():
    report = route_kill_switch_command(
        state=KillSwitchState(active=True),
        request=KillSwitchRequest(
            command="RESET",
            reason="unit test",
            emergency_state_clear=True,
            human_approval_valid=False,
        ),
    )

    assert report.approved is False
    assert "human_approval_required_to_reset_kill_switch" in report.blockers


def test_kill_switch_reset_with_approval():
    report = route_kill_switch_command(
        state=KillSwitchState(active=True),
        request=KillSwitchRequest(
            command="RESET",
            reason="unit test",
            emergency_state_clear=True,
            human_approval_valid=True,
            approved_by="Paulo",
        ),
    )

    assert report.approved is True
    assert report.active_after is False