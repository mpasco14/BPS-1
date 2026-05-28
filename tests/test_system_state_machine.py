from system_integration.system_state_machine import (
    StateTransitionRequest,
    SystemStateMachineState,
    evaluate_state_transition,
)


def test_state_machine_allows_config_to_paper_ready():
    decision = evaluate_state_transition(
        current=SystemStateMachineState(state="CONFIG_VALIDATION"),
        request=StateTransitionRequest(action="MARK_PAPER_READY", config_valid=True),
    )

    assert decision.approved is True
    assert decision.state_after == "PAPER_READY"


def test_state_machine_blocks_micro_live_without_approval():
    decision = evaluate_state_transition(
        current=SystemStateMachineState(state="LIVE_PREFLIGHT"),
        request=StateTransitionRequest(
            action="MARK_MICRO_LIVE_READY",
            live_preflight_passed=True,
            production_guard_passed=True,
            emergency_test_passed=True,
            human_approval_valid=False,
        ),
    )

    assert decision.approved is False
    assert "human_approval_required" in decision.blockers


def test_state_machine_allows_kill_switch_from_running():
    decision = evaluate_state_transition(
        current=SystemStateMachineState(state="RUNNING"),
        request=StateTransitionRequest(
            action="ACTIVATE_KILL_SWITCH",
            reason="unit",
        ),
    )

    assert decision.approved is True
    assert decision.state_after == "KILL_SWITCH_ACTIVE"