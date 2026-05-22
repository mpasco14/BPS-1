from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from dashboard.sentiment_panels import (
    build_sentiment_dashboard_snapshot,
    export_sentiment_dashboard_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build sentiment dashboard snapshot.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/sentiment")
    parser.add_argument("--name", default="sentiment_dashboard_latest")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    snapshot = build_sentiment_dashboard_snapshot()

    print(json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        paths = export_sentiment_dashboard_snapshot(
            snapshot,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Sentiment dashboard JSON: {paths['json']}")
        print(f"Sentiment dashboard HTML: {paths['html']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())