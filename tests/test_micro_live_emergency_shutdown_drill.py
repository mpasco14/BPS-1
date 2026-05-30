from micro_live.emergency_shutdown_drill import EmergencyShutdownDrillConfig, run_emergency_shutdown_drill


def test_emergency_shutdown_drill_passes(tmp_path):
    report = run_emergency_shutdown_drill(
        config=EmergencyShutdownDrillConfig(
            output_dir=tmp_path,
            emergency_stop_file=tmp_path / "emergency_stop.flag",
            require_emergency_stop_drill=True,
            require_kill_switch_writable=True,
        )
    )

    assert report.passed is True
    assert report.stop_file_created is True
    assert report.stop_file_removed is True