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


AttributionDimension = Literal[
    "strategy_source",
    "signal_source",
    "timeframe",
    "symbol",
    "regime",
    "sentiment_label",
]


class PnLAttributionItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    dimension: AttributionDimension
    name: str

    events_count: int = 0
    closed_events_count: int = 0

    realized_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    funding_usd: float = 0.0
    realized_net_pnl_usd: float = 0.0

    wins_count: int = 0
    losses_count: int = 0
    win_rate: float | None = None

    avg_net_pnl_usd: float | None = None
    contribution_pct: float | None = None


class PnLAttributionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "pnl_attribution_by_source"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    total_realized_net_pnl_usd: float = 0.0
    dimensions_count: int
    items_count: int

    items: list[dict[str, Any]] = Field(default_factory=list)


def value_for_dimension(event: ExposureLedgerEvent, dimension: AttributionDimension) -> str:
    value = getattr(event, dimension)

    if value is None or value == "":
        return "unknown"

    return str(value)


def build_pnl_attribution_report(
    *,
    events: list[ExposureLedgerEvent | dict[str, Any]],
    dimensions: list[AttributionDimension] | None = None,
) -> PnLAttributionReport:
    parsed_events = [
        item if isinstance(item, ExposureLedgerEvent) else ExposureLedgerEvent.model_validate(item)
        for item in events
    ]

    resolved_dimensions = dimensions or [
        "strategy_source",
        "signal_source",
        "timeframe",
        "symbol",
        "regime",
        "sentiment_label",
    ]

    groups: dict[tuple[str, str], list[ExposureLedgerEvent]] = defaultdict(list)

    for event in parsed_events:
        for dimension in resolved_dimensions:
            groups[(dimension, value_for_dimension(event, dimension))].append(event)

    total_net = sum(event.realized_pnl_usd - event.fees_usd + event.funding_usd for event in parsed_events)
    items: list[PnLAttributionItem] = []

    for (dimension, name), group_events in sorted(groups.items()):
        realized = sum(event.realized_pnl_usd for event in group_events)
        fees = sum(event.fees_usd for event in group_events)
        funding = sum(event.funding_usd for event in group_events)
        net = realized - fees + funding

        closed_events = [
            event
            for event in group_events
            if event.event_type in {"CLOSE", "REDUCE", "PNL_ADJUSTMENT"}
        ]

        wins = sum(1 for event in closed_events if event.realized_pnl_usd - event.fees_usd + event.funding_usd > 0)
        losses = sum(1 for event in closed_events if event.realized_pnl_usd - event.fees_usd + event.funding_usd < 0)

        closed_count = len(closed_events)

        win_rate = None
        avg_net = None

        if closed_count > 0:
            win_rate = wins / closed_count
            avg_net = net / closed_count

        contribution = None
        if abs(total_net) > 1e-12:
            contribution = net / total_net

        items.append(
            PnLAttributionItem(
                dimension=dimension,  # type: ignore[arg-type]
                name=name,
                events_count=len(group_events),
                closed_events_count=closed_count,
                realized_pnl_usd=round(realized, 8),
                fees_usd=round(fees, 8),
                funding_usd=round(funding, 8),
                realized_net_pnl_usd=round(net, 8),
                wins_count=wins,
                losses_count=losses,
                win_rate=round(win_rate, 8) if win_rate is not None else None,
                avg_net_pnl_usd=round(avg_net, 8) if avg_net is not None else None,
                contribution_pct=round(contribution, 8) if contribution is not None else None,
            )
        )

    return PnLAttributionReport(
        total_realized_net_pnl_usd=round(total_net, 8),
        dimensions_count=len(resolved_dimensions),
        items_count=len(items),
        items=[item.model_dump(mode="json") for item in items],
    )


def export_pnl_attribution_report(
    report: PnLAttributionReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "pnl_attribution_latest",
) -> Path:
    path = Path(output_dir or os.getenv("PNL_ATTRIBUTION_OUTPUT_DIR", "artifacts/portfolio"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path