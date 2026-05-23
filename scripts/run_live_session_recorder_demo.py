from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.live_session_recorder import (
    build_demo_live_session_events,
    build_live_session_summary,
    export_live_session_summary,
    record_live_session_event,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live session recorder demo.")

    parser.add_argument("--session-name", default="live_micro_demo")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--events-path", default="artifacts/live/live_session_demo_events.jsonl")
    parser.add_argument("--summary-path", default="artifacts/live/live_session_demo_summary.json")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    events = build_demo_live_session_events(session_name=args.session_name)
    summary = build_live_session_summary(events=events, session_name=args.session_name)

    print(json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        events_path = Path(args.events_path)

        if events_path.exists():
            events_path.unlink()

        for event in events:
            record_live_session_event(event, path=events_path)

        summary_path = export_live_session_summary(summary, path=args.summary_path)

        print(f"Live session events exported: {events_path}")
        print(f"Live session summary exported: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())