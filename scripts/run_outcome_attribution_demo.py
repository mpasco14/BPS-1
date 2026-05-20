from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.outcome_attribution import (
    TradeOutcomeInput,
    build_outcome_attribution_report,
    export_outcome_attribution_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run outcome attribution demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/journal")
    parser.add_argument("--name", default="outcome_demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    report = build_outcome_attribution_report(
        TradeOutcomeInput(
            trade_id="demo_trade_001",
            symbol="BTCUSDT",
            timeframe="5m",
            side="BUY",
            predicted_probability=0.72,
            expected_value_usd=0.5,
            realized_pnl_usd=1.2,
            fees_usd=0.1,
            expected_slippage_pct=0.0005,
            realized_slippage_pct=0.0004,
            latency_ms=220,
            regime="TRENDING_UP",
        )
    )

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_outcome_attribution_report(
            report,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Outcome attribution exported: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())