from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from portfolio_intelligence.exposure_ledger import ExposureLedgerEvent


load_dotenv()


PositionStatus = Literal["OPEN", "CLOSED", "REDUCED", "UNKNOWN"]


class PositionLifecycle(BaseModel):
    model_config = ConfigDict(extra="allow")

    position_id: str
    symbol: str
    timeframe: str
    side: str

    status: PositionStatus = "UNKNOWN"

    opened_at: datetime | None = None
    closed_at: datetime | None = None

    quantity_opened: float = 0.0
    quantity_closed: float = 0.0
    remaining_quantity: float = 0.0

    notional_opened_usd: float = 0.0
    notional_closed_usd: float = 0.0
    remaining_notional_usd: float = 0.0

    margin_opened_usd: float = 0.0
    margin_released_usd: float = 0.0

    realized_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    funding_usd: float = 0.0
    realized_net_pnl_usd: float = 0.0

    max_leverage_seen: int = 0
    events_count: int = 0

    strategy_source: str | None = None
    signal_source: str | None = None
    sentiment_label: str | None = None
    regime: str | None = None


class PositionLifecycleReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "position_lifecycle_tracker"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    positions_count: int
    open_positions_count: int
    closed_positions_count: int

    total_realized_net_pnl_usd: float = 0.0
    total_remaining_notional_usd: float = 0.0

    positions: list[dict[str, Any]] = Field(default_factory=list)


def position_key(event: ExposureLedgerEvent) -> str:
    if event.position_id:
        return event.position_id

    return f"{event.symbol}:{event.timeframe}:{event.side}"


def build_position_lifecycle_report(
    *,
    events: list[ExposureLedgerEvent | dict[str, Any]],
) -> PositionLifecycleReport:
    parsed_events = [
        item if isinstance(item, ExposureLedgerEvent) else ExposureLedgerEvent.model_validate(item)
        for item in events
    ]

    parsed_events = sorted(parsed_events, key=lambda item: item.timestamp)

    grouped: dict[str, list[ExposureLedgerEvent]] = defaultdict(list)

    for event in parsed_events:
        grouped[position_key(event)].append(event)

    positions: list[PositionLifecycle] = []

    for key, position_events in grouped.items():
        first = position_events[0]

        lifecycle = PositionLifecycle(
            position_id=key,
            symbol=first.symbol,
            timeframe=first.timeframe,
            side=first.side,
            strategy_source=first.strategy_source,
            signal_source=first.signal_source,
            sentiment_label=first.sentiment_label,
            regime=first.regime,
        )

        for event in position_events:
            lifecycle.events_count += 1
            lifecycle.max_leverage_seen = max(lifecycle.max_leverage_seen, event.leverage)

            lifecycle.realized_pnl_usd += event.realized_pnl_usd
            lifecycle.fees_usd += event.fees_usd
            lifecycle.funding_usd += event.funding_usd

            if event.event_type in {"OPEN", "INCREASE"}:
                if lifecycle.opened_at is None:
                    lifecycle.opened_at = event.timestamp

                lifecycle.quantity_opened += abs(event.quantity)
                lifecycle.notional_opened_usd += abs(event.notional_usd)
                lifecycle.margin_opened_usd += abs(event.margin_usd)

            if event.event_type in {"REDUCE", "CLOSE"}:
                lifecycle.quantity_closed += abs(event.quantity)
                lifecycle.notional_closed_usd += abs(event.notional_usd)
                lifecycle.margin_released_usd += abs(event.margin_usd)

                if event.event_type == "CLOSE":
                    lifecycle.closed_at = event.timestamp

        lifecycle.remaining_quantity = max(0.0, lifecycle.quantity_opened - lifecycle.quantity_closed)
        lifecycle.remaining_notional_usd = max(0.0, lifecycle.notional_opened_usd - lifecycle.notional_closed_usd)
        lifecycle.realized_net_pnl_usd = lifecycle.realized_pnl_usd - lifecycle.fees_usd + lifecycle.funding_usd

        if lifecycle.remaining_quantity <= 1e-12 or lifecycle.closed_at is not None:
            lifecycle.status = "CLOSED"
        elif lifecycle.quantity_closed > 0:
            lifecycle.status = "REDUCED"
        elif lifecycle.quantity_opened > 0:
            lifecycle.status = "OPEN"
        else:
            lifecycle.status = "UNKNOWN"

        positions.append(lifecycle)

    open_positions = [item for item in positions if item.status in {"OPEN", "REDUCED"}]
    closed_positions = [item for item in positions if item.status == "CLOSED"]

    return PositionLifecycleReport(
        positions_count=len(positions),
        open_positions_count=len(open_positions),
        closed_positions_count=len(closed_positions),
        total_realized_net_pnl_usd=round(sum(item.realized_net_pnl_usd for item in positions), 8),
        total_remaining_notional_usd=round(sum(item.remaining_notional_usd for item in positions), 8),
        positions=[item.model_dump(mode="json") for item in positions],
    )


def export_position_lifecycle_report(
    report: PositionLifecycleReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "position_lifecycle_latest",
) -> Path:
    path = Path(output_dir or os.getenv("POSITION_LIFECYCLE_OUTPUT_DIR", "artifacts/portfolio"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path