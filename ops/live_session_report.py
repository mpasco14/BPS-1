from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LiveSessionEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_name: str = "live_micro_session"
    symbol: str = "BTCUSDT"
    side: str
    quantity: float
    price: float | None = None
    notional_usd: float = 0.0
    margin_usd: float = 0.0
    status: str = "PLANNED"
    pnl_usd: float = 0.0
    fee_usd: float = 0.0
    raw: dict[str, Any] = Field(default_factory=dict)


class LiveSessionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_session_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str
    dry_run: bool = True
    submitted: bool = False

    events_count: int = 0
    planned_orders: int = 0
    submitted_orders: int = 0
    blocked_orders: int = 0

    gross_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    net_pnl_usd: float = 0.0

    events: list[dict[str, Any]] = Field(default_factory=list)


def build_live_session_report(
    *,
    session_name: str,
    events: list[LiveSessionEvent | dict[str, Any]],
    dry_run: bool = True,
    submitted: bool = False,
) -> LiveSessionReport:
    parsed_events = [
        item if isinstance(item, LiveSessionEvent) else LiveSessionEvent.model_validate(item)
        for item in events
    ]

    gross_pnl = sum(float(item.pnl_usd) for item in parsed_events)
    fees = sum(float(item.fee_usd) for item in parsed_events)

    return LiveSessionReport(
        session_name=session_name,
        dry_run=dry_run,
        submitted=submitted,
        events_count=len(parsed_events),
        planned_orders=sum(1 for item in parsed_events if item.status == "PLANNED"),
        submitted_orders=sum(1 for item in parsed_events if item.status == "SUBMITTED"),
        blocked_orders=sum(1 for item in parsed_events if item.status == "BLOCKED"),
        gross_pnl_usd=gross_pnl,
        fees_usd=fees,
        net_pnl_usd=gross_pnl - fees,
        events=[item.model_dump(mode="json") for item in parsed_events],
    )


def export_live_session_report(
    report: LiveSessionReport,
    *,
    output_dir: str | Path = "artifacts/live",
    name: str = "live_micro_session_latest",
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name.replace('/', '_').replace(chr(92), '_')}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path