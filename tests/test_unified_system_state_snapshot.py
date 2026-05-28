from system_integration.runtime_context import build_integrated_runtime_context
from system_integration.system_state_machine import SystemStateMachineState
from system_integration.system_state_snapshot import build_unified_system_state_snapshot


def test_unified_system_state_snapshot_healthy():
    snapshot = build_unified_system_state_snapshot(
        runtime_context=build_integrated_runtime_context(environment="development", execution_mode="paper"),
        system_state=SystemStateMachineState(state="PAPER_READY"),
    )

    assert snapshot.healthy is True
    assert snapshot.status == "PASS"


def test_unified_system_state_snapshot_blocks_kill_switch_state():
    snapshot = build_unified_system_state_snapshot(
        runtime_context=build_integrated_runtime_context(environment="development", execution_mode="paper"),
        system_state=SystemStateMachineState(state="KILL_SWITCH_ACTIVE"),
    )

    assert snapshot.healthy is False
    assert snapshot.status == "FAIL"