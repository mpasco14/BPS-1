from argparse import Namespace

from scripts.run_testnet_session import build_demo_events, build_session_payload, load_events_from_args


def test_build_demo_events():
    events = build_demo_events("unit_demo")

    assert len(events) == 3
    assert events[0].session_name == "unit_demo"


def test_build_session_payload():
    events = build_demo_events("unit_demo")

    payload = build_session_payload(
        events=events,
        session_name="unit_demo",
    )

    assert payload["source"] == "testnet_session_runner"
    assert "session" in payload
    assert "quality" in payload


def test_load_events_from_args_demo():
    args = Namespace(
        demo=True,
        events_jsonl=None,
        session_name="unit_demo",
    )

    events = load_events_from_args(args)

    assert len(events) == 3