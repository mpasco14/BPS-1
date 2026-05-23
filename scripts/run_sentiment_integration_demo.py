from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.sentiment_strategy_health import build_sentiment_strategy_health_report, export_sentiment_strategy_health_report
from ops.strategy_health import StrategyHealthInput
from sentiment.sentiment_schema import SentimentFeatureRow
from strategy.no_trade_engine import NoTradeInput
from strategy.sentiment_no_trade_adapter import evaluate_no_trade_with_sentiment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run sentiment integration demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/sentiment")
    parser.add_argument("--name", default="sentiment_integration_demo")

    return parser.parse_args()


def sample_sentiment_row() -> SentimentFeatureRow:
    return SentimentFeatureRow(
        symbol="BTCUSDT",
        timeframe="5m",
        btc_sentiment_index=70,
        fear_greed_value=70,
        fear_greed_label="greed",
        sentiment_confidence=0.75,
        items_count=5,
        bullish_count=3,
        bearish_count=1,
        neutral_count=1,
    )


def main() -> int:
    args = parse_args()
    sentiment = sample_sentiment_row()

    no_trade = evaluate_no_trade_with_sentiment(
        base_input=NoTradeInput(
            model_confidence=0.72,
            expected_value_usd=0.5,
            spread_pct=0.0002,
            liquidity_usd=100000,
            regime="TRENDING_UP",
            risk_state_status="OK",
        ),
        sentiment_row=sentiment,
        intended_side="LONG",
    )

    health = build_sentiment_strategy_health_report(
        strategy_input=StrategyHealthInput(
            trades_count=50,
            net_pnl_usd=10,
            max_drawdown_pct=0.03,
            profit_factor=1.3,
            win_rate=0.58,
            fill_rate=0.75,
            rejection_rate=0.02,
            expected_calibration_error=0.08,
            ood_rate=0.05,
            discipline_score=0.95,
            risk_state_status="OK",
        ),
        sentiment_row=sentiment,
    )

    output = {
        "no_trade": no_trade.model_dump(mode="json"),
        "sentiment_strategy_health": health.model_dump(mode="json"),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.export:
        path = export_sentiment_strategy_health_report(
            health,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Sentiment strategy health exported: {path}")

    return 0 if no_trade.should_trade and health.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())