from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


FillEventType = Literal["FILL", "PARTIAL_FILL", "REJECTION"]
FillMonitorStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetFillMonitorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_readiness")

    min_fill_rate: float = 0.70
    max_rejection_rate: float = 0.10
    max_avg_slippage_pct: float = 0.005


class TestnetFillEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    order_id: str
    event_type: FillEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    expected_price: float | None = None
    fill_price: float | None = None
    requested_qty: float = 0.0
    filled_qty: float = 0.0

    rejection_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestnetFillMonitorReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_fill_rejection_monitoring"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: FillMonitorStatus
    passed: bool

    events_count: int
    fill_events_count: int
    partial_fill_events_count: int
    rejection_events_count: int

    requested_qty_total: float
    filled_qty_total: float

    fill_rate: float
    rejection_rate: float
    avg_slippage_pct: float

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    events: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any]


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_testnet_fill_monitor_config() -> TestnetFillMonitorConfig:
    return TestnetFillMonitorConfig(
        output_dir=Path(os.getenv("TESTNET_FILL_MONITOR_OUTPUT_DIR", "artifacts/testnet_readiness")),
        min_fill_rate=env_float("TESTNET_FILL_MIN_FILL_RATE", 0.70),
        max_rejection_rate=env_float("TESTNET_FILL_MAX_REJECTION_RATE", 0.10),
        max_avg_slippage_pct=env_float("TESTNET_FILL_MAX_AVG_SLIPPAGE_PCT", 0.005),
    )


def slippage_pct(event: TestnetFillEvent) -> float | None:
    if event.expected_price is None or event.fill_price is None or event.expected_price <= 0:
        return None

    return abs(event.fill_price - event.expected_price) / event.expected_price


def monitor_testnet_fills_and_rejections(
    *,
    events: list[TestnetFillEvent | dict[str, Any]],
    config: TestnetFillMonitorConfig | None = None,
) -> TestnetFillMonitorReport:
    resolved_config = config or load_testnet_fill_monitor_config()
    parsed = [
        item if isinstance(item, TestnetFillEvent) else TestnetFillEvent.model_validate(item)
        for item in events
    ]

    blockers: list[str] = []
    warnings: list[str] = []

    fill_events = [item for item in parsed if item.event_type == "FILL"]
    partial_events = [item for item in parsed if item.event_type == "PARTIAL_FILL"]
    rejection_events = [item for item in parsed if item.event_type == "REJECTION"]

    requested_qty_by_order: dict[str, float] = {}

    for item in parsed:
        if item.event_type == "REJECTION":
            continue

        requested_qty_by_order[item.order_id] = max(
            requested_qty_by_order.get(item.order_id, 0.0),
            max(0.0, item.requested_qty),
        )

    requested_total = sum(requested_qty_by_order.values())

    filled_qty_by_order: dict[str, float] = {}

    for item in parsed:
        if item.event_type not in {"FILL", "PARTIAL_FILL"}:
            continue

        filled_qty_by_order[item.order_id] = (
            filled_qty_by_order.get(item.order_id, 0.0)
            + max(0.0, item.filled_qty)
        )

    filled_total = sum(filled_qty_by_order.values())

    fill_rate = filled_total / requested_total if requested_total > 0 else 0.0
    rejection_rate = len(rejection_events) / len(parsed) if parsed else 0.0

    slippages = [
        value
        for item in parsed
        if (value := slippage_pct(item)) is not None
    ]

    avg_slippage = sum(slippages) / len(slippages) if slippages else 0.0

    if fill_rate < resolved_config.min_fill_rate:
        blockers.append("fill_rate_below_minimum")

    if rejection_rate > resolved_config.max_rejection_rate:
        blockers.append("rejection_rate_above_limit")

    if avg_slippage > resolved_config.max_avg_slippage_pct:
        warnings.append("avg_slippage_above_limit")

    if not parsed:
        blockers.append("fill_monitor_events_missing")

    passed = not blockers

    return TestnetFillMonitorReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        events_count=len(parsed),
        fill_events_count=len(fill_events),
        partial_fill_events_count=len(partial_events),
        rejection_events_count=len(rejection_events),
        requested_qty_total=round(requested_total, 12),
        filled_qty_total=round(filled_total, 12),
        fill_rate=round(fill_rate, 8),
        rejection_rate=round(rejection_rate, 8),
        avg_slippage_pct=round(avg_slippage, 8),
        blockers=blockers,
        warnings=warnings,
        events=[item.model_dump(mode="json") for item in parsed],
        config=resolved_config.model_dump(mode="json"),
    )

def build_demo_fill_events() -> list[TestnetFillEvent]:
    return [
        TestnetFillEvent(
            event_id="fill_1",
            order_id="order_demo",
            event_type="PARTIAL_FILL",
            expected_price=60000,
            fill_price=60002,
            requested_qty=0.001,
            filled_qty=0.0005,
        ),
        TestnetFillEvent(
            event_id="fill_2",
            order_id="order_demo",
            event_type="FILL",
            expected_price=60000,
            fill_price=60003,
            requested_qty=0.001,
            filled_qty=0.0005,
        ),
    ]


def export_testnet_fill_monitor_report(
    report: TestnetFillMonitorReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_fill_monitor_report",
) -> Path:
    config = load_testnet_fill_monitor_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path