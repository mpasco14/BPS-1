from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.data_quality_gate import DataQualityInput, evaluate_data_quality, export_data_quality_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run data quality gate demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/governance")
    parser.add_argument("--name", default="data_quality_latest")

    return parser.parse_args()


def build_demo_input() -> DataQualityInput:
    now = datetime.now(timezone.utc)

    return DataQualityInput(
        now=now,
        symbol="BTCUSDT",
        timeframe="5m",
        candle_timestamp=now,
        orderbook_timestamp=now,
        last_price=60000,
        reference_price=60001,
        spread_pct=0.0002,
        liquidity_usd=100000,
        websocket_connected=True,
        orderbook_tradeable=True,
        missing_features=[],
        feature_values={
            "technical_score": 0.7,
            "sentiment_score": 0.1,
            "onchain_score": 0.2,
        },
    )


def main() -> int:
    args = parse_args()

    report = evaluate_data_quality(data=build_demo_input())

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_data_quality_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Data quality report exported: {path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())