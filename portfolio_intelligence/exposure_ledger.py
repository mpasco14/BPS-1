from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ExposureEventType = Literal[
    "OPEN",
    "INCREASE",
    "REDUCE",
    "CLOSE",
    "FEE",
    "FUNDING",
    "PNL_ADJUSTMENT",
]

ExposureSide = Literal["LONG", "SHORT", "FLAT"]


class ExposureLedgerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/portfolio")
    ledger_file: Path = Path("artifacts/portfolio/exposure_ledger.jsonl")


class ExposureLedgerEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    event_type: ExposureEventType
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"
    side: ExposureSide = "LONG"

    position_id: str | None = None
    order_id: str | None = None
    trade_id: str | None = None
    decision_id: str | None = None

    quantity: float = 0.0
    price: float | None = None
    notional_usd: float = 0.0
    margin_usd: float = 0.0
    leverage: int = 1

    realized_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    funding_usd: float = 0.0

    strategy_source: str | None = None
    signal_source: str | None = None
    sentiment_label: str | None = None
    regime: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class ExposureLedger(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "unified_exposure_ledger"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    events_count: int
    events: list[dict[str, Any]] = Field(default_factory=list)


class ExposureLedgerSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "exposure_ledger_summary"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    events_count: int

    total_abs_notional_usd: float = 0.0
    net_notional_usd: float = 0.0
    gross_long_notional_usd: float = 0.0
    gross_short_notional_usd: float = 0.0

    total_margin_usd: float = 0.0
    max_leverage_seen: int = 0

    realized_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    funding_usd: float = 0.0
    realized_net_pnl_usd: float = 0.0

    symbols_count: int = 0
    timeframes_count: int = 0

    exposure_by_symbol: dict[str, float] = Field(default_factory=dict)
    exposure_by_timeframe: dict[str, float] = Field(default_factory=dict)
    margin_by_symbol: dict[str, float] = Field(default_factory=dict)

    config: dict[str, Any] = Field(default_factory=dict)


def load_exposure_ledger_config() -> ExposureLedgerConfig:
    return ExposureLedgerConfig(
        output_dir=Path(os.getenv("EXPOSURE_LEDGER_OUTPUT_DIR", "artifacts/portfolio")),
        ledger_file=Path(os.getenv("EXPOSURE_LEDGER_FILE", "artifacts/portfolio/exposure_ledger.jsonl")),
    )


def signed_base_notional(event: ExposureLedgerEvent) -> float:
    if event.side == "LONG":
        return abs(event.notional_usd)

    if event.side == "SHORT":
        return -abs(event.notional_usd)

    return 0.0


def exposure_delta(event: ExposureLedgerEvent) -> float:
    base = signed_base_notional(event)

    if event.event_type in {"OPEN", "INCREASE"}:
        return base

    if event.event_type in {"REDUCE", "CLOSE"}:
        return -base

    return 0.0


def margin_delta(event: ExposureLedgerEvent) -> float:
    if event.event_type in {"OPEN", "INCREASE"}:
        return abs(event.margin_usd)

    if event.event_type in {"REDUCE", "CLOSE"}:
        return -abs(event.margin_usd)

    return 0.0


def build_exposure_ledger(
    *,
    events: list[ExposureLedgerEvent | dict[str, Any]],
) -> ExposureLedger:
    parsed = [
        item if isinstance(item, ExposureLedgerEvent) else ExposureLedgerEvent.model_validate(item)
        for item in events
    ]

    parsed = sorted(parsed, key=lambda item: item.timestamp)

    return ExposureLedger(
        events_count=len(parsed),
        events=[item.model_dump(mode="json") for item in parsed],
    )


def summarize_exposure_ledger(
    *,
    ledger: ExposureLedger | dict[str, Any] | None = None,
    events: list[ExposureLedgerEvent | dict[str, Any]] | None = None,
) -> ExposureLedgerSummary:
    config = load_exposure_ledger_config()

    if ledger is not None:
        parsed_ledger = ledger if isinstance(ledger, ExposureLedger) else ExposureLedger.model_validate(ledger)
        parsed_events = [ExposureLedgerEvent.model_validate(item) for item in parsed_ledger.events]
    else:
        parsed_events = [
            item if isinstance(item, ExposureLedgerEvent) else ExposureLedgerEvent.model_validate(item)
            for item in (events or [])
        ]

    exposure_by_symbol: dict[str, float] = defaultdict(float)
    exposure_by_timeframe: dict[str, float] = defaultdict(float)
    margin_by_symbol: dict[str, float] = defaultdict(float)

    realized_pnl = 0.0
    fees = 0.0
    funding = 0.0
    max_leverage = 0

    for event in parsed_events:
        delta = exposure_delta(event)
        margin = margin_delta(event)

        exposure_by_symbol[event.symbol] += delta
        exposure_by_timeframe[event.timeframe] += delta
        margin_by_symbol[event.symbol] += margin

        realized_pnl += event.realized_pnl_usd
        fees += event.fees_usd
        funding += event.funding_usd
        max_leverage = max(max_leverage, event.leverage)

    exposure_by_symbol = {
        symbol: round(value, 8)
        for symbol, value in exposure_by_symbol.items()
        if abs(value) > 1e-9
    }

    exposure_by_timeframe = {
        timeframe: round(value, 8)
        for timeframe, value in exposure_by_timeframe.items()
        if abs(value) > 1e-9
    }

    margin_by_symbol = {
        symbol: round(max(0.0, value), 8)
        for symbol, value in margin_by_symbol.items()
        if abs(value) > 1e-9
    }

    net_notional = sum(exposure_by_symbol.values())
    gross_long = sum(value for value in exposure_by_symbol.values() if value > 0)
    gross_short = abs(sum(value for value in exposure_by_symbol.values() if value < 0))
    total_abs = gross_long + gross_short
    total_margin = sum(margin_by_symbol.values())

    return ExposureLedgerSummary(
        events_count=len(parsed_events),
        total_abs_notional_usd=round(total_abs, 8),
        net_notional_usd=round(net_notional, 8),
        gross_long_notional_usd=round(gross_long, 8),
        gross_short_notional_usd=round(gross_short, 8),
        total_margin_usd=round(total_margin, 8),
        max_leverage_seen=max_leverage,
        realized_pnl_usd=round(realized_pnl, 8),
        fees_usd=round(fees, 8),
        funding_usd=round(funding, 8),
        realized_net_pnl_usd=round(realized_pnl - fees + funding, 8),
        symbols_count=len(exposure_by_symbol),
        timeframes_count=len(exposure_by_timeframe),
        exposure_by_symbol=dict(exposure_by_symbol),
        exposure_by_timeframe=dict(exposure_by_timeframe),
        margin_by_symbol=dict(margin_by_symbol),
        config=config.model_dump(mode="json"),
    )


def append_exposure_event(
    event: ExposureLedgerEvent,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_exposure_ledger_config()
    output_path = Path(path or config.ledger_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def load_exposure_events(path: str | Path | None = None) -> list[ExposureLedgerEvent]:
    config = load_exposure_ledger_config()
    input_path = Path(path or config.ledger_file)

    if not input_path.exists():
        return []

    events: list[ExposureLedgerEvent] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            events.append(ExposureLedgerEvent.model_validate(json.loads(line)))

    return events


def export_exposure_ledger_summary(
    summary: ExposureLedgerSummary,
    *,
    output_dir: str | Path | None = None,
    name: str = "exposure_ledger_summary_latest",
) -> Path:
    config = load_exposure_ledger_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def demo_exposure_events() -> list[ExposureLedgerEvent]:
    return [
        ExposureLedgerEvent(
            event_id="demo_open_1",
            event_type="OPEN",
            symbol="BTCUSDT",
            timeframe="5m",
            side="LONG",
            position_id="pos_1",
            quantity=0.01,
            price=60000,
            notional_usd=600,
            margin_usd=20,
            leverage=30,
            strategy_source="technical_breakout",
            signal_source="signal_engine",
            sentiment_label="greed",
            regime="TRENDING_UP",
        ),
        ExposureLedgerEvent(
            event_id="demo_fee_1",
            event_type="FEE",
            symbol="BTCUSDT",
            timeframe="5m",
            side="LONG",
            position_id="pos_1",
            fees_usd=0.24,
            strategy_source="technical_breakout",
            signal_source="signal_engine",
            sentiment_label="greed",
            regime="TRENDING_UP",
        ),
        ExposureLedgerEvent(
            event_id="demo_close_1",
            event_type="CLOSE",
            symbol="BTCUSDT",
            timeframe="5m",
            side="LONG",
            position_id="pos_1",
            quantity=0.01,
            price=60300,
            notional_usd=600,
            margin_usd=20,
            leverage=30,
            realized_pnl_usd=3.0,
            strategy_source="technical_breakout",
            signal_source="signal_engine",
            sentiment_label="greed",
            regime="TRENDING_UP",
        ),
    ]