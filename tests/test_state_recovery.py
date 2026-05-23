from infra.state_recovery import (
    RuntimeStateSnapshot,
    build_state_recovery_report,
    export_runtime_state_snapshot,
    load_runtime_state_snapshot,
)


def test_state_recovery_ready_clean_snapshot():
    report = build_state_recovery_report(
        snapshot=RuntimeStateSnapshot(
            risk_state_status="OK",
            open_orders=[],
            open_positions=[],
        )
    )

    assert report.passed is True
    assert report.status == "READY"


def test_state_recovery_blocks_risk_not_ok():
    report = build_state_recovery_report(
        snapshot=RuntimeStateSnapshot(
            risk_state_status="BLOCKED",
            open_orders=[],
            open_positions=[],
        )
    )

    assert report.passed is False
    assert "risk_state_not_ok" in report.blockers


def test_state_snapshot_export_and_load(tmp_path):
    path = tmp_path / "state.json"
    snapshot = RuntimeStateSnapshot(session_name="unit")

    export_runtime_state_snapshot(snapshot, path=path)
    loaded = load_runtime_state_snapshot(path)

    assert path.exists()
    assert loaded is not None
    assert loaded.session_name == "unit"