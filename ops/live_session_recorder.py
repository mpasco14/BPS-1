from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


LiveSessionEventType = Literal[
    "SESSION_START",
    "SESSION_END",
    "PLANNED",
    "BLOCKED",
    "SUBMITTED",
    "PARTIAL_FILL",
    "FILLED",
    "CANCELED",
    "REJECTED",
    "ERROR",
    "RISK_UPDATE",
]


class LiveSessionRecorderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live")
    events_file: Path = Path("artifacts/live/live_session_events.jsonl")
    summary_file: Path = Path("artifacts/live/live_session_summary.json")


class LiveRecordedEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_session_recorder"

    event_id: str
    session_name: str = "live_micro_session"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    event_type: LiveSessionEventType
    status: str | None = None

    symbol: str = "BTCUSDT"
    timeframe: str | None = None
    side: str | None = None

    order_id: str | int | None = None
    client_order_id: str | None = None
    signal_id: str | None = None
    decision_id: str | None = None
    model_version: str | None = None

    quantity: float = 0.0
    filled_quantity: float = 0.0
    price: float | None = None
    executed_price: float | None = None

    notional_usd: float = 0.0
    margin_usd: float = 0.0
    leverage: int | None = None

    gross_pnl_usd: float = 0.0
    fee_usd: float = 0.0
    net_pnl_usd: float = 0.0

    latency_ms: float | None = None
    slippage_pct: float | None = None

    regime: str | None = None
    sentiment_index: float | None = None
    fear_greed_label: str | None = None

    preflight_passed: bool | None = None
    live_guard_passed: bool | None = None
    no_trade_passed: bool | None = None
    risk_state_status: str | None = None

    risk_blockers: list[str] = Field(default_factory=list)
    guard_blockers: list[str] = Field(default_factory=list)
    no_trade_blockers: list[str] = Field(default_factory=list)

    raw: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LiveSessionRecorderSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_session_recorder_summary"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str
    events_count: int

    started_at: datetime | None = None
    ended_at: datetime | None = None

    planned_count: int = 0
    blocked_count: int = 0
    submitted_count: int = 0
    partial_fill_count: int = 0
    filled_count: int = 0
    canceled_count: int = 0
    rejected_count: int = 0
    error_count: int = 0

    gross_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    net_pnl_usd: float = 0.0

    total_notional_usd: float = 0.0
    max_margin_usd: float = 0.0
    max_leverage: int | None = None

    event_type_distribution: dict[str, int] = Field(default_factory=dict)
    symbol_distribution: dict[str, int] = Field(default_factory=dict)
    timeframe_distribution: dict[str, int] = Field(default_factory=dict)

    events: list[dict[str, Any]] = Field(default_factory=list)


def load_live_session_recorder_config() -> LiveSessionRecorderConfig:
    return LiveSessionRecorderConfig(
        output_dir=Path(os.getenv("LIVE_SESSION_OUTPUT_DIR", "artifacts/live")),
        events_file=Path(os.getenv("LIVE_SESSION_EVENTS_FILE", "artifacts/live/live_session_events.jsonl")),
        summary_file=Path(os.getenv("LIVE_SESSION_SUMMARY_FILE", "artifacts/live/live_session_summary.json")),
    )


def record_live_session_event(
    event: LiveRecordedEvent | dict[str, Any],
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_live_session_recorder_config()
    output_path = Path(path or config.events_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    parsed = event if isinstance(event, LiveRecordedEvent) else LiveRecordedEvent.model_validate(event)

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def load_live_session_events(
    path: str | Path | None = None,
    *,
    session_name: str | None = None,
) -> list[LiveRecordedEvent]:
    config = load_live_session_recorder_config()
    input_path = Path(path or config.events_file)

    if not input_path.exists():
        return []

    events: list[LiveRecordedEvent] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            event = LiveRecordedEvent.model_validate(json.loads(line))

            if session_name and event.session_name != session_name:
                continue

            events.append(event)

    return sorted(events, key=lambda item: item.timestamp)


def build_live_session_summary(
    *,
    events: list[LiveRecordedEvent | dict[str, Any]],
    session_name: str | None = None,
) -> LiveSessionRecorderSummary:
    parsed_events = [
        item if isinstance(item, LiveRecordedEvent) else LiveRecordedEvent.model_validate(item)
        for item in events
    ]

    if session_name:
        parsed_events = [item for item in parsed_events if item.session_name == session_name]

    parsed_events = sorted(parsed_events, key=lambda item: item.timestamp)

    resolved_session_name = session_name or (parsed_events[0].session_name if parsed_events else "live_micro_session")

    type_counter = Counter(item.event_type for item in parsed_events)
    symbol_counter = Counter(item.symbol for item in parsed_events)
    timeframe_counter = Counter(item.timeframe or "unknown" for item in parsed_events)

    started_at = parsed_events[0].timestamp if parsed_events else None
    ended_at = parsed_events[-1].timestamp if parsed_events else None

    max_leverage_values = [item.leverage for item in parsed_events if item.leverage is not None]

    return LiveSessionRecorderSummary(
        session_name=resolved_session_name,
        events_count=len(parsed_events),
        started_at=started_at,
        ended_at=ended_at,
        planned_count=type_counter.get("PLANNED", 0),
        blocked_count=type_counter.get("BLOCKED", 0),
        submitted_count=type_counter.get("SUBMITTED", 0),
        partial_fill_count=type_counter.get("PARTIAL_FILL", 0),
        filled_count=type_counter.get("FILLED", 0),
        canceled_count=type_counter.get("CANCELED", 0),
        rejected_count=type_counter.get("REJECTED", 0),
        error_count=type_counter.get("ERROR", 0),
        gross_pnl_usd=round(sum(item.gross_pnl_usd for item in parsed_events), 8),
        fees_usd=round(sum(item.fee_usd for item in parsed_events), 8),
        net_pnl_usd=round(sum(item.net_pnl_usd for item in parsed_events), 8),
        total_notional_usd=round(sum(item.notional_usd for item in parsed_events if item.event_type in {"SUBMITTED", "FILLED"}), 8),
        max_margin_usd=max([item.margin_usd for item in parsed_events], default=0.0),
        max_leverage=max(max_leverage_values) if max_leverage_values else None,
        event_type_distribution=dict(type_counter),
        symbol_distribution=dict(symbol_counter),
        timeframe_distribution=dict(timeframe_counter),
        events=[item.model_dump(mode="json") for item in parsed_events],
    )


def export_live_session_summary(
    summary: LiveSessionRecorderSummary,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_live_session_recorder_config()
    output_path = Path(path or config.summary_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def build_demo_live_session_events(session_name: str = "live_micro_demo") -> list[LiveRecordedEvent]:
    return [
        LiveRecordedEvent(
            event_id="demo_session_start",
            session_name=session_name,
            event_type="SESSION_START",
            status="STARTED",
        ),
        LiveRecordedEvent(
            event_id="demo_planned_1",
            session_name=session_name,
            event_type="PLANNED",
            status="PLANNED",
            symbol="BTCUSDT",
            timeframe="5m",
            side="LONG",
            quantity=0.01,
            price=60000,
            notional_usd=600,
            margin_usd=20,
            leverage=30,
            preflight_passed=True,
            live_guard_passed=True,
            no_trade_passed=True,
            risk_state_status="OK",
            regime="TRENDING_UP",
            sentiment_index=68,
            fear_greed_label="greed",
        ),
            LiveRecordedEvent(
            event_id="demo_submitted_1",
            session_name=session_name,
            event_type="SUBMITTED",
            status="NEW",
            symbol="BTCUSDT",
            timeframe="5m",
            side="LONG",
            order_id="order-demo-1",
            quantity=0.01,
            price=60000,
            notional_usd=600,
            margin_usd=20,
            leverage=30,
            latency_ms=220,
            preflight_passed=True,
            live_guard_passed=True,
            no_trade_passed=True,
            risk_state_status="OK",
            regime="TRENDING_UP",
            sentiment_index=68,
            fear_greed_label="greed",
        ),
        LiveRecordedEvent(
            event_id="demo_filled_1",
            session_name=session_name,
            event_type="FILLED",
            status="FILLED",
            symbol="BTCUSDT",
            timeframe="5m",
            side="LONG",
            order_id="order-demo-1",
            quantity=0.01,
            filled_quantity=0.01,
            price=60000,
            executed_price=60020,
            notional_usd=600,
            margin_usd=20,
            leverage=30,
            gross_pnl_usd=1.2,
            fee_usd=0.12,
            net_pnl_usd=1.08,
            latency_ms=260,
            slippage_pct=0.00033,
            regime="TRENDING_UP",
            sentiment_index=68,
            fear_greed_label="greed",
        ),
        LiveRecordedEvent(
            event_id="demo_session_end",
            session_name=session_name,
            event_type="SESSION_END",
            status="ENDED",
        ),
    ]