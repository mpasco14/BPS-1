from execution.cancel_order import OpenOrderState
from ops.emergency_shutdown import (
    EmergencyShutdownConfig,
    build_safe_mode_state,
    cancel_orders_for_shutdown,
    clear_safe_mode_state,
    execute_emergency_shutdown,
    export_emergency_shutdown_report,
    load_safe_mode_state,
    persist_safe_mode_state,
)


def sample_order():
    return OpenOrderState(
        symbol="BTCUSDT",
        client_order_id="client-1",
        order_id=123,
        side="BUY",
        price=60000,
        quantity=0.01,
        status="NEW",
        timeframe="5m",
    )


def test_build_safe_mode_state():
    state = build_safe_mode_state(
        reason="unit_test",
        block_new_entries=True,
    )

    assert state.safe_mode_active is True
    assert state.new_entries_blocked is True
    assert state.kill_switch_reason == "unit_test"


def test_persist_and_load_safe_mode_state(tmp_path):
    path = tmp_path / "state.json"
    state = build_safe_mode_state(reason="unit_test")

    persist_safe_mode_state(state, path=path)
    loaded = load_safe_mode_state(path)

    assert loaded is not None
    assert loaded.kill_switch_reason == "unit_test"


def test_clear_safe_mode_state(tmp_path):
    path = tmp_path / "state.json"
    state = build_safe_mode_state(reason="unit_test")

    persist_safe_mode_state(state, path=path)

    assert clear_safe_mode_state(path) is True
    assert load_safe_mode_state(path) is None


def test_cancel_orders_for_shutdown_dry_run():
    results = cancel_orders_for_shutdown(
        open_orders=[sample_order()],
        reason="unit_test",
        dry_run=True,
    )

    assert len(results) == 1
    assert results[0].attempted is False
    assert results[0].success is True


def test_execute_emergency_shutdown_dry_run(tmp_path):
    config = EmergencyShutdownConfig(
        output_dir=tmp_path,
        state_file=tmp_path / "state.json",
        dry_run=True,
    )

    report = execute_emergency_shutdown(
        open_orders=[sample_order()],
        reason="unit_test",
        config=config,
    )

    assert report.status == "DRY_RUN"
    assert report.dry_run is True
    assert report.open_orders_received == 1
    assert report.passed is True
    assert (tmp_path / "state.json").exists()


def test_execute_emergency_shutdown_disabled(tmp_path):
    config = EmergencyShutdownConfig(
        enabled=False,
        output_dir=tmp_path,
        state_file=tmp_path / "state.json",
    )

    report = execute_emergency_shutdown(
        reason="unit_test",
        config=config,
    )

    assert report.status == "FAILED"
    assert report.passed is False


def test_export_emergency_shutdown_report(tmp_path):
    config = EmergencyShutdownConfig(
        output_dir=tmp_path,
        state_file=tmp_path / "state.json",
        dry_run=True,
    )

    report = execute_emergency_shutdown(
        reason="unit_test",
        config=config,
    )

    path = export_emergency_shutdown_report(
        report,
        output_dir=tmp_path,
        name="unit_test_shutdown",
    )

    assert path.exists()