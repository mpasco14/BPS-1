from datetime import datetime, timedelta, timezone

from live_ops.live_session_supervisor import (
    LiveSessionSupervisorConfig,
    LiveSessionTelemetry,
    supervise_live_session,
)


def test_live_session_supervisor_running_clean_session():
    report = supervise_live_session(
        telemetry=LiveSessionTelemetry(
            session_name="unit",
            environment="testnet",
        )
    )

    assert report.allowed_to_continue is True
    assert report.status == "RUNNING"


def test_live_session_supervisor_blocks_kill_switch():
    report = supervise_live_session(
        telemetry=LiveSessionTelemetry(
            session_name="unit",
            kill_switch_active=True,
        )
    )

    assert report.allowed_to_continue is False
    assert "kill_switch_active" in report.blockers


def test_live_session_supervisor_blocks_stale_heartbeat():
    report = supervise_live_session(
        telemetry=LiveSessionTelemetry(
            session_name="unit",
            heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=120),
        ),
        config=LiveSessionSupervisorConfig(max_heartbeat_age_seconds=60),
    )

    assert report.allowed_to_continue is False
    assert "heartbeat_stale" in report.blockers