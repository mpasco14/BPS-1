from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ops.live_session_recorder import LiveRecordedEvent, load_live_session_events


load_dotenv()


LivePerformanceStatus = Literal["PASS", "WARN", "FAIL"]


class LivePerformanceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live")

    min_trades: int = 5
    min_fill_rate: float = 0.60
    max_rejection_rate: float = 0.10
    max_cancel_rate: float = 0.30
    max_avg_slippage_pct: float = 0.002
    max_avg_latency_ms: float = 1500.0


class LivePerformanceReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_performance_analyzer"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str
    status: LivePerformanceStatus
    passed: bool

    events_count: int
    submitted_count: int
    filled_count: int
    canceled_count: int
    rejected_count: int
    blocked_count: int

    fill_rate: float = 0.0
    cancel_rate: float = 0.0
    rejection_rate: float = 0.0

    gross_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    net_pnl_usd: float = 0.0

    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_usd: float = 0.0
    average_trade_pnl_usd: float = 0.0

    average_slippage_pct: float | None = None
    average_latency_ms: float | None = None

    pnl_by_timeframe: dict[str, float] = Field(default_factory=dict)
    pnl_by_regime: dict[str, float] = Field(default_factory=dict)
    pnl_by_sentiment_label: dict[str, float] = Field(default_factory=dict)

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    config: dict[str, Any] = Field(default_factory=dict)


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


def load_live_performance_config() -> LivePerformanceConfig:
    return LivePerformanceConfig(
        output_dir=Path(os.getenv("LIVE_PERFORMANCE_OUTPUT_DIR", "artifacts/live")),
        min_trades=env_int("LIVE_PERFORMANCE_MIN_TRADES", 5),
        min_fill_rate=env_float("LIVE_PERFORMANCE_MIN_FILL_RATE", 0.60),
        max_rejection_rate=env_float("LIVE_PERFORMANCE_MAX_REJECTION_RATE", 0.10),
        max_cancel_rate=env_float("LIVE_PERFORMANCE_MAX_CANCEL_RATE", 0.30),
        max_avg_slippage_pct=env_float("LIVE_PERFORMANCE_MAX_AVG_SLIPPAGE_PCT", 0.002),
        max_avg_latency_ms=env_float("LIVE_PERFORMANCE_MAX_AVG_LATENCY_MS", 1500),
    )


def average(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None]

    if not clean:
        return None

    return sum(clean) / len(clean)


def calculate_max_drawdown(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)

    return round(max_drawdown, 8)


def calculate_profit_factor(pnl_values: list[float]) -> float:
    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))

    if gross_loss == 0:
        return round(gross_profit, 8) if gross_profit > 0 else 0.0

    return round(gross_profit / gross_loss, 8)


def build_live_performance_report(
    *,
    events: list[LiveRecordedEvent | dict[str, Any]] | None = None,
    events_path: str | Path | None = None,
    session_name: str = "live_micro_session",
    config: LivePerformanceConfig | None = None,
) -> LivePerformanceReport:
    resolved_config = config or load_live_performance_config()

    if events is None:
        parsed_events = load_live_session_events(events_path, session_name=session_name)
    else:
        parsed_events = [
            item if isinstance(item, LiveRecordedEvent) else LiveRecordedEvent.model_validate(item)
            for item in events
        ]
        parsed_events = [item for item in parsed_events if item.session_name == session_name]

    submitted_count = sum(1 for item in parsed_events if item.event_type == "SUBMITTED")
    filled_events = [item for item in parsed_events if item.event_type == "FILLED"]
    canceled_count = sum(1 for item in parsed_events if item.event_type == "CANCELED")
    rejected_count = sum(1 for item in parsed_events if item.event_type == "REJECTED")
    blocked_count = sum(1 for item in parsed_events if item.event_type == "BLOCKED")

    filled_count = len(filled_events)

    order_outcomes = submitted_count + canceled_count + rejected_count
    fill_rate = filled_count / order_outcomes if order_outcomes else 0.0
    cancel_rate = canceled_count / order_outcomes if order_outcomes else 0.0
    rejection_rate = rejected_count / order_outcomes if order_outcomes else 0.0

    pnl_values = [item.net_pnl_usd for item in filled_events]
    wins = [value for value in pnl_values if value > 0]

    gross_pnl = sum(item.gross_pnl_usd for item in filled_events)
    fees = sum(item.fee_usd for item in filled_events)
    net_pnl = sum(pnl_values)

    slippage_values = [item.slippage_pct for item in parsed_events if item.slippage_pct is not None]
    latency_values = [item.latency_ms for item in parsed_events if item.latency_ms is not None]

    pnl_by_timeframe: dict[str, float] = defaultdict(float)
    pnl_by_regime: dict[str, float] = defaultdict(float)
    pnl_by_sentiment_label: dict[str, float] = defaultdict(float)

    for item in filled_events:
        pnl_by_timeframe[item.timeframe or "unknown"] += item.net_pnl_usd
        pnl_by_regime[item.regime or "unknown"] += item.net_pnl_usd
        pnl_by_sentiment_label[item.fear_greed_label or "unknown"] += item.net_pnl_usd

    avg_slippage = average(slippage_values)
    avg_latency = average(latency_values)

    blockers: list[str] = []
    warnings: list[str] = []

    if filled_count < resolved_config.min_trades:
        warnings.append("filled_trades_below_minimum")

    if fill_rate < resolved_config.min_fill_rate:
        warnings.append("fill_rate_below_minimum")

    if rejection_rate > resolved_config.max_rejection_rate:
        blockers.append("rejection_rate_above_limit")

    if cancel_rate > resolved_config.max_cancel_rate:
        warnings.append("cancel_rate_above_limit")

    if avg_slippage is not None and avg_slippage > resolved_config.max_avg_slippage_pct:
        warnings.append("average_slippage_above_limit")

    if avg_latency is not None and avg_latency > resolved_config.max_avg_latency_ms:
        warnings.append("average_latency_above_limit")

    passed = not blockers

    if blockers:
        status: LivePerformanceStatus = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    return LivePerformanceReport(
        session_name=session_name,
        status=status,
        passed=passed,
        events_count=len(parsed_events),
        submitted_count=submitted_count,
        filled_count=filled_count,
        canceled_count=canceled_count,
        rejected_count=rejected_count,
        blocked_count=blocked_count,
        fill_rate=round(fill_rate, 8),
        cancel_rate=round(cancel_rate, 8),
        rejection_rate=round(rejection_rate, 8),
        gross_pnl_usd=round(gross_pnl, 8),
        fees_usd=round(fees, 8),
        net_pnl_usd=round(net_pnl, 8),
        win_rate=round(len(wins) / filled_count, 8) if filled_count else 0.0,
        profit_factor=calculate_profit_factor(pnl_values),
        max_drawdown_usd=calculate_max_drawdown(pnl_values),
        average_trade_pnl_usd=round(net_pnl / filled_count, 8) if filled_count else 0.0,
        average_slippage_pct=round(avg_slippage, 8) if avg_slippage is not None else None,
        average_latency_ms=round(avg_latency, 8) if avg_latency is not None else None,
        pnl_by_timeframe={key: round(value, 8) for key, value in pnl_by_timeframe.items()},
        pnl_by_regime={key: round(value, 8) for key, value in pnl_by_regime.items()},
        pnl_by_sentiment_label={key: round(value, 8) for key, value in pnl_by_sentiment_label.items()},
        blockers=blockers,
        warnings=warnings,
        config=resolved_config.model_dump(mode="json"),
    )


def export_live_performance_report(
    report: LivePerformanceReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "live_performance_latest",
) -> Path:
    config = load_live_performance_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path