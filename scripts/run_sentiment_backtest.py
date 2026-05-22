from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backtesting.sentiment_backtest import (
    SentimentBacktestSample,
    export_sentiment_backtest_report,
    run_sentiment_backtest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run sentiment feature backtest demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/sentiment")
    parser.add_argument("--name", default="sentiment_backtest_demo")

    return parser.parse_args()


def demo_samples() -> list[SentimentBacktestSample]:
    return [
        SentimentBacktestSample(
            sentiment_features={
                "btc_sentiment_index": 72,
                "sentiment_confidence": 0.75,
            },
            future_return_pct=0.01,
        ),
        SentimentBacktestSample(
            sentiment_features={
                "btc_sentiment_index": 28,
                "sentiment_confidence": 0.80,
            },
            future_return_pct=-0.008,
        ),
        SentimentBacktestSample(
            sentiment_features={
                "btc_sentiment_index": 50,
                "sentiment_confidence": 0.90,
            },
            future_return_pct=0.004,
        ),
    ]


def main() -> int:
    args = parse_args()

    report = run_sentiment_backtest(samples=demo_samples())

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_sentiment_backtest_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Sentiment backtest exported: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())