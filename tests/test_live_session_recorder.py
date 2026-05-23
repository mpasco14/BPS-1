from ops.live_session_recorder import (
    LiveRecordedEvent,
    build_demo_live_session_events,
    build_live_session_summary,
    load_live_session_events,
    record_live_session_event,
)


def test_build_live_session_summary():
    events = build_demo_live_session_events("unit_session")

    summary = build_live_session_summary(events=events, session_name="unit_session")

    assert summary.session_name == "unit_session"
    assert summary.events_count == 5
    assert summary.filled_count == 1
    assert summary.net_pnl_usd == 1.08


def test_record_and_load_live_session_events(tmp_path):
    path = tmp_path / "events.jsonl"

    event = LiveRecordedEvent(
        event_id="unit_event",
        session_name="unit",
        event_type="FILLED",
        status="FILLED",
        net_pnl_usd=1.0,
    )

    record_live_session_event(event, path=path)
    loaded = load_live_session_events(path, session_name="unit")

    assert path.exists()
    assert len(loaded) == 1
    assert loaded[0].event_id == "unit_event"