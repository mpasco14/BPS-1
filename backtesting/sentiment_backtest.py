from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from sentiment.sentiment_schema import SentimentFeatureRow


load_dotenv()


SentimentBacktestSide = Literal["LONG", "SHORT", "FLAT"]


class SentimentBacktestConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    long_threshold: float = 60.0
    short_threshold: float = 40.0
    min_confidence: float = 0.50
    notional_usd: float = 100.0
    fee_rate: float = 0.0004


class SentimentBacktestSample(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"

    sentiment_features: dict[str, Any]
    future_return_pct: float


class SentimentBacktestTrade(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    symbol: str
    timeframe: str

    side: SentimentBacktestSide
    sentiment_index: float
    confidence: float
    future_return_pct: float

    gross_pnl_usd: float
    fees_usd: float
    net_pnl_usd: float
    is_win: bool


class SentimentBacktestReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_backtest"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    samples_count: int
    trades_count: int

    net_pnl_usd: float = 0.0
    gross_pnl_usd: float = 0.0
    fees_usd: float = 0.0

    hit_rate: float = 0.0
    average_trade_pnl_usd: float = 0.0

    trades_by_side: dict[str, int] = Field(default_factory=dict)
    pnl_by_side: dict[str, float] = Field(default_factory=dict)

    trades: list[dict[str, Any]] = Field(default_factory=list)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_sentiment_backtest_config() -> SentimentBacktestConfig:
    return SentimentBacktestConfig(
        long_threshold=env_float("SENTIMENT_BACKTEST_LONG_THRESHOLD", 60),
        short_threshold=env_float("SENTIMENT_BACKTEST_SHORT_THRESHOLD", 40),
        min_confidence=env_float("SENTIMENT_BACKTEST_MIN_CONFIDENCE", 0.50),
        notional_usd=env_float("SENTIMENT_BACKTEST_NOTIONAL_USD", 100),
        fee_rate=env_float("SENTIMENT_BACKTEST_FEE_RATE", 0.0004),
    )


def row_to_sample(
    *,
    row: SentimentFeatureRow | dict[str, Any],
    future_return_pct: float,
) -> SentimentBacktestSample:
    parsed = row if isinstance(row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(row)

    return SentimentBacktestSample(
        timestamp=parsed.timestamp,
        symbol=parsed.symbol,
        timeframe=parsed.timeframe,
        sentiment_features=parsed.model_dump(mode="json"),
        future_return_pct=future_return_pct,
    )


def decide_sentiment_side(
    *,
    sentiment_index: float,
    confidence: float,
    config: SentimentBacktestConfig,
) -> SentimentBacktestSide:
    if confidence < config.min_confidence:
        return "FLAT"

    if sentiment_index >= config.long_threshold:
        return "LONG"

    if sentiment_index <= config.short_threshold:
        return "SHORT"

    return "FLAT"


def simulate_sentiment_trade(
    *,
    sample: SentimentBacktestSample,
    config: SentimentBacktestConfig,
) -> SentimentBacktestTrade | None:
    features = sample.sentiment_features

    sentiment_index = float(features.get("btc_sentiment_index", 50))
    confidence = float(features.get("sentiment_confidence", 0))

    side = decide_sentiment_side(
        sentiment_index=sentiment_index,
        confidence=confidence,
        config=config,
    )

    if side == "FLAT":
        return None

    direction = 1 if side == "LONG" else -1
    gross_pnl = config.notional_usd * sample.future_return_pct * direction
    fees = config.notional_usd * config.fee_rate * 2
    net_pnl = gross_pnl - fees

    return SentimentBacktestTrade(
        timestamp=sample.timestamp,
        symbol=sample.symbol,
        timeframe=sample.timeframe,
        side=side,
        sentiment_index=sentiment_index,
        confidence=confidence,
        future_return_pct=sample.future_return_pct,
        gross_pnl_usd=gross_pnl,
        fees_usd=fees,
        net_pnl_usd=net_pnl,
        is_win=net_pnl > 0,
    )


def run_sentiment_backtest(
    *,
    samples: list[SentimentBacktestSample | dict[str, Any]],
    config: SentimentBacktestConfig | None = None,
) -> SentimentBacktestReport:
    resolved_config = config or load_sentiment_backtest_config()

    parsed_samples = [
        sample if isinstance(sample, SentimentBacktestSample) else SentimentBacktestSample.model_validate(sample)
        for sample in samples
    ]

    trades: list[SentimentBacktestTrade] = []

    for sample in parsed_samples:
        trade = simulate_sentiment_trade(
            sample=sample,
            config=resolved_config,
        )

        if trade:
            trades.append(trade)

    gross = sum(trade.gross_pnl_usd for trade in trades)
    fees = sum(trade.fees_usd for trade in trades)
    net = sum(trade.net_pnl_usd for trade in trades)

    wins = sum(1 for trade in trades if trade.is_win)

    trades_by_side: dict[str, int] = defaultdict(int)
    pnl_by_side: dict[str, float] = defaultdict(float)

    for trade in trades:
        trades_by_side[trade.side] += 1
        pnl_by_side[trade.side] += trade.net_pnl_usd

    trades_count = len(trades)

    return SentimentBacktestReport(
        samples_count=len(parsed_samples),
        trades_count=trades_count,
        gross_pnl_usd=round(gross, 8),
        fees_usd=round(fees, 8),
        net_pnl_usd=round(net, 8),
        hit_rate=round(wins / trades_count, 8) if trades_count else 0.0,
        average_trade_pnl_usd=round(net / trades_count, 8) if trades_count else 0.0,
        trades_by_side=dict(trades_by_side),
        pnl_by_side={key: round(value, 8) for key, value in pnl_by_side.items()},
        trades=[trade.model_dump(mode="json") for trade in trades],
    )


def export_sentiment_backtest_report(
    report: SentimentBacktestReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "sentiment_backtest_latest",
) -> Path:
    path = Path(output_dir or os.getenv("SENTIMENT_BACKTEST_OUTPUT_DIR", "artifacts/sentiment"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path