from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from sentiment.sentiment_orchestrator import (
    build_demo_raw_items,
    export_sentiment_orchestrator_report,
    run_sentiment_orchestrator,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run sentiment orchestrator demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/sentiment")
    parser.add_argument("--name", default="sentiment_orchestrator_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    report = run_sentiment_orchestrator(
        raw_items=build_demo_raw_items(),
        asset="BTCUSDT",
        timeframe="5m",
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_sentiment_orchestrator_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Sentiment orchestrator exported: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())