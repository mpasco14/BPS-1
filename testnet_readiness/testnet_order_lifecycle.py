from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


OrderLifecycleEventType = Literal[
    "PLANNED",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELED",
    "REJECTED",
]

LifecycleStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetOrderLifecycleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_readiness")

    require_ack: bool = True
    allow_partial_fill: bool = True
    max_rejected_orders: int = 0


class TestnetOrderLifecycleEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    order_id: str
    event_type: OrderLifecycleEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    symbol: str = "BTCUSDT"
    side: str = "BUY"

    requested_qty: float = 0.0
    filled_qty: float = 0.0
    price: float | None = None
    rejection_reason: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class TestnetOrderLifecycleReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_order_lifecycle_validation"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: LifecycleStatus
    passed: bool

    orders_count: int
    submitted_count: int
    acknowledged_count: int
    filled_count: int
    partial_count: int
    canceled_count: int
    rejected_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    orders: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_testnet_order_lifecycle_config() -> TestnetOrderLifecycleConfig:
    return TestnetOrderLifecycleConfig(
        output_dir=Path(os.getenv("TESTNET_ORDER_LIFECYCLE_OUTPUT_DIR", "artifacts/testnet_readiness")),
        require_ack=env_bool("TESTNET_ORDER_REQUIRE_ACK", True),
        allow_partial_fill=env_bool("TESTNET_ORDER_ALLOW_PARTIAL_FILL", True),
        max_rejected_orders=env_int("TESTNET_ORDER_MAX_REJECTED_ORDERS", 0),
    )


def group_events_by_order(
    events: list[TestnetOrderLifecycleEvent],
) -> dict[str, list[TestnetOrderLifecycleEvent]]:
    grouped: dict[str, list[TestnetOrderLifecycleEvent]] = {}

    for event in sorted(events, key=lambda item: item.timestamp):
        grouped.setdefault(event.order_id, []).append(event)

    return grouped


def validate_testnet_order_lifecycle(
    *,
    events: list[TestnetOrderLifecycleEvent | dict[str, Any]],
    config: TestnetOrderLifecycleConfig | None = None,
) -> TestnetOrderLifecycleReport:
    resolved_config = config or load_testnet_order_lifecycle_config()
    parsed = [
        item if isinstance(item, TestnetOrderLifecycleEvent) else TestnetOrderLifecycleEvent.model_validate(item)
        for item in events
    ]

    grouped = group_events_by_order(parsed)

    blockers: list[str] = []
    warnings: list[str] = []

    submitted_count = 0
    acknowledged_count = 0
    filled_count = 0
    partial_count = 0
    canceled_count = 0
    rejected_count = 0

    for order_id, order_events in grouped.items():
        types = [item.event_type for item in order_events]

        if "PLANNED" not in types:
            warnings.append(f"{order_id}:planned_event_missing")

        if "SUBMITTED" in types:
            submitted_count += 1

        if "ACKNOWLEDGED" in types:
            acknowledged_count += 1

        if "FILLED" in types:
            filled_count += 1

        if "PARTIALLY_FILLED" in types:
            partial_count += 1

        if "CANCELED" in types:
            canceled_count += 1

        if "REJECTED" in types:
            rejected_count += 1

        if "SUBMITTED" not in types:
            blockers.append(f"{order_id}:submitted_event_missing")

        if resolved_config.require_ack and "ACKNOWLEDGED" not in types and "REJECTED" not in types:
            blockers.append(f"{order_id}:acknowledged_event_missing")

        if "REJECTED" in types:
            warnings.append(f"{order_id}:order_rejected")

        if "PARTIALLY_FILLED" in types and not resolved_config.allow_partial_fill:
            blockers.append(f"{order_id}:partial_fill_not_allowed")

        terminal = {"FILLED", "CANCELED", "REJECTED"}
        if not any(item in terminal for item in types):
            warnings.append(f"{order_id}:terminal_event_missing")

    if rejected_count > resolved_config.max_rejected_orders:
        blockers.append("rejected_orders_above_limit")

    passed = not blockers

    return TestnetOrderLifecycleReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        orders_count=len(grouped),
        submitted_count=submitted_count,
        acknowledged_count=acknowledged_count,
        filled_count=filled_count,
        partial_count=partial_count,
        canceled_count=canceled_count,
        rejected_count=rejected_count,
        blockers=blockers,
        warnings=warnings,
        orders={
            order_id: [event.model_dump(mode="json") for event in order_events]
            for order_id, order_events in grouped.items()
        },
        config=resolved_config.model_dump(mode="json"),
    )


def build_demo_lifecycle_events() -> list[TestnetOrderLifecycleEvent]:
    return [
        TestnetOrderLifecycleEvent(event_id="e1", order_id="order_demo", event_type="PLANNED", requested_qty=0.001, price=60000),
        TestnetOrderLifecycleEvent(event_id="e2", order_id="order_demo", event_type="SUBMITTED", requested_qty=0.001, price=60000),
        TestnetOrderLifecycleEvent(event_id="e3", order_id="order_demo", event_type="ACKNOWLEDGED", requested_qty=0.001, price=60000),
        TestnetOrderLifecycleEvent(event_id="e4", order_id="order_demo", event_type="PARTIALLY_FILLED", requested_qty=0.001, filled_qty=0.0005, price=60000),
        TestnetOrderLifecycleEvent(event_id="e5", order_id="order_demo", event_type="FILLED", requested_qty=0.001, filled_qty=0.001, price=60000),
    ]


def export_testnet_order_lifecycle_report(
    report: TestnetOrderLifecycleReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_order_lifecycle_report",
) -> Path:
    config = load_testnet_order_lifecycle_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path