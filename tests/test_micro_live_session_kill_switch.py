from micro_live_session.kill_switch_validation import validate_micro_live_kill_switch
from micro_live_session.session_models import MicroLiveSessionConfig


def test_micro_live_kill_switch_validation_passes(tmp_path):
    report = validate_micro_live_kill_switch(
        config=MicroLiveSessionConfig(
            emergency_stop_file=tmp_path / "stop.flag",
            require_kill_switch=True,
        )
    )

    assert report.passed is True
    assert report.kill_switch_file_created is True
    assert report.kill_switch_file_removed is True