from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.live_performance_analyzer import (
    build_live_performance_report,
    export_live_performance_report,
)
from ops.live_session_recorder import build_demo_live_session_events


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live performance analyzer.")

    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--events-path", default=None)
    parser.add_argument("--session-name", default="live_micro_demo")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/live")
    parser.add_argument("--name", default="live_performance_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    events = build_demo_live_session_events(args.session_name) if args.demo else None

    report = build_live_performance_report(
        events=events,
        events_path=args.events_path,
        session_name=args.session_name,
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_live_performance_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Live performance report exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())