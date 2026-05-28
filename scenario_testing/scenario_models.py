from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ScenarioStatus = Literal["PASS", "WARN", "FAIL", "EXPECTED_BLOCKED"]
ScenarioKind = Literal[
    "historical_replay",
    "volatility_shock",
    "trend_regime",
    "chop_sideways",
    "news_sentiment_shock",
]

MarketRegime = Literal[
    "unknown",
    "trend_up",
    "trend_down",
    "high_volatility",
    "sideways",
    "news_shock",
]

SignalDirection = Literal["BUY", "SELL", "HOLD"]


class MarketCandle(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    symbol: str = "BTCUSDT"
    timeframe: str = "5m"

    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    sentiment_index: float = 50.0
    fear_greed_value: float = 50.0
    sentiment_confidence: float = 0.5
    sentiment_regime: str = "neutral"

    news_event: bool = False
    regime: MarketRegime = "unknown"

    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayStepResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    step_index: int
    timestamp: datetime

    symbol: str
    timeframe: str

    close: float
    price_change_pct: float = 0.0

    direction: SignalDirection = "HOLD"
    confidence: float = 0.0
    edge: float = 0.0

    approved: bool = False
    blocked: bool = False
    dry_run: bool = True

    step_pnl_usd: float = 0.0
    cumulative_pnl_usd: float = 0.0
    equity_usd: float = 0.0
    drawdown_pct: float = 0.0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    components: dict[str, Any] = Field(default_factory=dict)


class ScenarioTestReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "scenario_test_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    scenario_name: str
    scenario_kind: ScenarioKind

    status: ScenarioStatus
    passed: bool
    expected_blocked: bool = False

    candles_count: int = 0
    steps_count: int = 0

    approved_signals_count: int = 0
    blocked_signals_count: int = 0
    hold_signals_count: int = 0

    total_pnl_usd: float = 0.0
    final_equity_usd: float = 0.0
    max_drawdown_pct: float = 0.0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    steps: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def pct_change(previous: float, current: float) -> float:
    if previous == 0:
        return 0.0

    return (current - previous) / previous


def direction_from_price_change(
    *,
    change_pct: float,
    threshold_pct: float,
) -> SignalDirection:
    if change_pct >= threshold_pct:
        return "BUY"

    if change_pct <= -threshold_pct:
        return "SELL"

    return "HOLD"


def confidence_from_move(change_pct: float) -> float:
    return round(min(0.95, max(0.0, 0.55 + abs(change_pct) * 25)), 8)


def edge_from_move(change_pct: float) -> float:
    return round(max(0.0, abs(change_pct) * 4), 8)


def generate_demo_candles(
    *,
    pattern: Literal["uptrend", "downtrend", "sideways", "volatility", "news_shock"] = "uptrend",
    count: int = 12,
    start_price: float = 60000.0,
    symbol: str = "BTCUSDT",
    timeframe: str = "5m",
) -> list[MarketCandle]:
    candles: list[MarketCandle] = []
    current = start_price
    now = datetime.now(timezone.utc).replace(microsecond=0)

    for index in range(count):
        if pattern == "uptrend":
            change = 0.0035
            regime: MarketRegime = "trend_up"
            sentiment_regime = "greed"
            sentiment_index = 65.0

        elif pattern == "downtrend":
            change = -0.0035
            regime = "trend_down"
            sentiment_regime = "fear"
            sentiment_index = 35.0

        elif pattern == "sideways":
            change = 0.0004 if index % 2 == 0 else -0.00035
            regime = "sideways"
            sentiment_regime = "neutral"
            sentiment_index = 50.0

        elif pattern == "volatility":
            moves = [0.002, -0.018, 0.021, -0.016, 0.014, -0.012, 0.019, -0.015, 0.004, -0.003, 0.002, -0.002]
            change = moves[index % len(moves)]
            regime = "high_volatility"
            sentiment_regime = "neutral"
            sentiment_index = 50.0

        else:
            moves = [0.001, 0.001, -0.022, -0.018, 0.006, 0.003, -0.004, 0.002, 0.001, -0.001, 0.002, 0.001]
            change = moves[index % len(moves)]
            regime = "news_shock" if index in {2, 3} else "unknown"
            sentiment_regime = "extreme_fear" if index in {2, 3} else "neutral"
            sentiment_index = 12.0 if index in {2, 3} else 50.0

        open_price = current
        close_price = current * (1 + change)
        high = max(open_price, close_price) * 1.001
        low = min(open_price, close_price) * 0.999

        candles.append(
            MarketCandle(
                timestamp=now + timedelta(minutes=5 * index),
                symbol=symbol,
                timeframe=timeframe,
                open=round(open_price, 8),
                high=round(high, 8),
                low=round(low, 8),
                close=round(close_price, 8),
                volume=100 + index,
                sentiment_index=sentiment_index,
                fear_greed_value=sentiment_index,
                sentiment_confidence=0.80,
                sentiment_regime=sentiment_regime,
                news_event=pattern == "news_shock" and index in {2, 3},
                regime=regime,
            )
        )

        current = close_price

    return candles


def export_scenario_report(
    report: ScenarioTestReport,
    *,
    output_dir: str | Path | None = None,
    name: str | None = None,
) -> Path:
    path = Path(output_dir or os.getenv("SCENARIO_TESTING_OUTPUT_DIR", "artifacts/scenario_testing"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = (name or report.scenario_name).replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path