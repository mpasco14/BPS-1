from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()

__test__ = False


EvidenceEventType = Literal[
    "SESSION_STARTED",
    "HEARTBEAT",
    "ORDER_PLANNED",
    "ORDER_SUBMITTED",
    "ORDER_ACK",
    "ORDER_PARTIAL_FILL",
    "ORDER_FILL",
    "ORDER_REJECTED",
    "ORDER_CANCELED",
    "POSITION_SNAPSHOT",
    "SESSION_ENDED",
    "ERROR",
    "KILL_SWITCH",
    "SAFE_MODE",
]

EvidenceStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetEvidenceCollectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_supervision")

    require_order_ack: bool = True
    require_fill_or_cancel: bool = True
    require_final_flat: bool = True

    max_rejection_rate: float = 0.10
    max_avg_slippage_pct: float = 0.005


class TestnetEvidenceEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    event_type: EvidenceEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str = "testnet_session"
    order_id: str | None = None

    symbol: str = "BTCUSDT"
    side: str | None = None

    expected_price: float | None = None
    actual_price: float | None = None

    requested_qty: float = 0.0
    filled_qty: float = 0.0

    position_qty: float = 0.0
    position_notional_usd: float = 0.0

    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestnetEvidenceCollectionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "real_testnet_evidence_collector"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: EvidenceStatus
    passed: bool

    session_name: str

    events_count: int
    heartbeat_count: int

    orders_planned_count: int
    orders_submitted_count: int
    order_ack_count: int
    fill_count: int
    partial_fill_count: int
    cancel_count: int
    rejection_count: int
    error_count: int

    requested_qty_total: float
    filled_qty_total: float
    fill_rate: float
    rejection_rate: float
    avg_slippage_pct: float

    final_position_qty: float
    final_position_notional_usd: float
    final_flat: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    events: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any]


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


def load_testnet_evidence_collector_config() -> TestnetEvidenceCollectorConfig:
    return TestnetEvidenceCollectorConfig(
        output_dir=Path(os.getenv("TESTNET_EVIDENCE_OUTPUT_DIR", "artifacts/testnet_supervision")),
        require_order_ack=env_bool("TESTNET_EVIDENCE_REQUIRE_ORDER_ACK", True),
        require_fill_or_cancel=env_bool("TESTNET_EVIDENCE_REQUIRE_FILL_OR_CANCEL", True),
        require_final_flat=env_bool("TESTNET_EVIDENCE_REQUIRE_FINAL_FLAT", True),
        max_rejection_rate=env_float("TESTNET_EVIDENCE_MAX_REJECTION_RATE", 0.10),
        max_avg_slippage_pct=env_float("TESTNET_EVIDENCE_MAX_AVG_SLIPPAGE_PCT", 0.005),
    )


def evidence_slippage_pct(event: TestnetEvidenceEvent) -> float | None:
    if event.expected_price is None or event.actual_price is None:
        return None

    if event.expected_price <= 0:
        return None

    return abs(event.actual_price - event.expected_price) / event.expected_price


def build_demo_testnet_evidence_events(
    *,
    session_name: str = "demo_supervised_testnet",
) -> list[TestnetEvidenceEvent]:
    return [
        TestnetEvidenceEvent(
            event_id="session_start",
            event_type="SESSION_STARTED",
            session_name=session_name,
            message="Demo supervised testnet session started.",
        ),
        TestnetEvidenceEvent(
            event_id="heartbeat_1",
            event_type="HEARTBEAT",
            session_name=session_name,
            message="Runner heartbeat OK.",
        ),
        TestnetEvidenceEvent(
            event_id="order_planned_1",
            event_type="ORDER_PLANNED",
            session_name=session_name,
            order_id="demo_order_1",
            side="BUY",
            expected_price=60000,
            requested_qty=0.001,
        ),
        TestnetEvidenceEvent(
            event_id="order_submitted_1",
            event_type="ORDER_SUBMITTED",
            session_name=session_name,
            order_id="demo_order_1",
            side="BUY",
            expected_price=60000,
            requested_qty=0.001,
        ),
        TestnetEvidenceEvent(
            event_id="order_ack_1",
            event_type="ORDER_ACK",
            session_name=session_name,
            order_id="demo_order_1",
            side="BUY",
            expected_price=60000,
            requested_qty=0.001,
        ),
        TestnetEvidenceEvent(
            event_id="order_partial_fill_1",
            event_type="ORDER_PARTIAL_FILL",
            session_name=session_name,
            order_id="demo_order_1",
            side="BUY",
            expected_price=60000,
            actual_price=60002,
            requested_qty=0.001,
            filled_qty=0.0005,
        ),
        TestnetEvidenceEvent(
            event_id="order_fill_1",
            event_type="ORDER_FILL",
            session_name=session_name,
            order_id="demo_order_1",
            side="BUY",
            expected_price=60000,
            actual_price=60003,
            requested_qty=0.001,
            filled_qty=0.0005,
        ),
        TestnetEvidenceEvent(
            event_id="position_snapshot_flat",
            event_type="POSITION_SNAPSHOT",
            session_name=session_name,
            position_qty=0.0,
            position_notional_usd=0.0,
            message="Final position flat.",
        ),
        TestnetEvidenceEvent(
            event_id="session_end",
            event_type="SESSION_ENDED",
            session_name=session_name,
            message="Demo supervised testnet session ended.",
        ),
    ]


def collect_testnet_evidence(
    *,
    events: list[TestnetEvidenceEvent | dict[str, Any]],
    config: TestnetEvidenceCollectorConfig | None = None,
) -> TestnetEvidenceCollectionReport:
    resolved_config = config or load_testnet_evidence_collector_config()

    parsed = [
        item if isinstance(item, TestnetEvidenceEvent) else TestnetEvidenceEvent.model_validate(item)
        for item in events
    ]

    parsed = sorted(parsed, key=lambda item: item.timestamp)

    session_name = parsed[0].session_name if parsed else "unknown"

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    heartbeat_count = sum(1 for item in parsed if item.event_type == "HEARTBEAT")
    planned = [item for item in parsed if item.event_type == "ORDER_PLANNED"]
    submitted = [item for item in parsed if item.event_type == "ORDER_SUBMITTED"]
    ack = [item for item in parsed if item.event_type == "ORDER_ACK"]
    fills = [item for item in parsed if item.event_type == "ORDER_FILL"]
    partials = [item for item in parsed if item.event_type == "ORDER_PARTIAL_FILL"]
    cancels = [item for item in parsed if item.event_type == "ORDER_CANCELED"]
    rejections = [item for item in parsed if item.event_type == "ORDER_REJECTED"]
    errors = [item for item in parsed if item.event_type == "ERROR"]

    requested_qty_by_order: dict[str, float] = {}
    filled_qty_by_order: dict[str, float] = {}

    for item in parsed:
        if not item.order_id:
            continue

        if item.event_type in {
            "ORDER_PLANNED",
            "ORDER_SUBMITTED",
            "ORDER_ACK",
            "ORDER_PARTIAL_FILL",
            "ORDER_FILL",
        }:
            requested_qty_by_order[item.order_id] = max(
                requested_qty_by_order.get(item.order_id, 0.0),
                max(0.0, item.requested_qty),
            )

        if item.event_type in {"ORDER_PARTIAL_FILL", "ORDER_FILL"}:
            filled_qty_by_order[item.order_id] = (
                filled_qty_by_order.get(item.order_id, 0.0)
                + max(0.0, item.filled_qty)
            )

    requested_total = sum(requested_qty_by_order.values())
    filled_total = sum(filled_qty_by_order.values())

    fill_rate = filled_total / requested_total if requested_total > 0 else 0.0
    rejection_rate = len(rejections) / max(1, len(submitted) + len(rejections))

    slippages = [
        value
        for item in parsed
        if (value := evidence_slippage_pct(item)) is not None
    ]

    avg_slippage = sum(slippages) / len(slippages) if slippages else 0.0

    final_position_qty = 0.0
    final_position_notional = 0.0

    position_snapshots = [
        item for item in parsed if item.event_type == "POSITION_SNAPSHOT"
    ]

    if position_snapshots:
        final_position_qty = position_snapshots[-1].position_qty
        final_position_notional = position_snapshots[-1].position_notional_usd

        final_flat = (
            abs(final_position_qty) <= 1e-12
            and abs(final_position_notional) <= 1e-9
        )
    else:
        final_flat = False if resolved_config.require_final_flat else True

    if not parsed:
        blockers.append("evidence_events_missing")

    if submitted and resolved_config.require_order_ack and not ack:
        blockers.append("order_ack_missing")

    if submitted and resolved_config.require_fill_or_cancel and not fills and not cancels:
        blockers.append("fill_or_cancel_missing")

    if resolved_config.require_final_flat and not final_flat:
        blockers.append("final_position_not_flat")

    if rejection_rate > resolved_config.max_rejection_rate:
        blockers.append("rejection_rate_above_limit")

    if avg_slippage > resolved_config.max_avg_slippage_pct:
        warnings.append("avg_slippage_above_limit")

    if errors:
        blockers.append("error_events_detected")

    if heartbeat_count == 0:
        warnings.append("heartbeat_events_missing")

    if not position_snapshots:
        warnings.append("position_snapshot_missing")

    recommendations.append("Guardar evidências de ordem, ACK, fill/cancel e snapshot final.")
    recommendations.append("Se houver rejeição ou erro, repetir sessão curta antes de aumentar duração.")

    passed = not blockers

    return TestnetEvidenceCollectionReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        session_name=session_name,
        events_count=len(parsed),
        heartbeat_count=heartbeat_count,
        orders_planned_count=len(planned),
        orders_submitted_count=len(submitted),
        order_ack_count=len(ack),
        fill_count=len(fills),
        partial_fill_count=len(partials),
        cancel_count=len(cancels),
        rejection_count=len(rejections),
        error_count=len(errors),
        requested_qty_total=round(requested_total, 12),
        filled_qty_total=round(filled_total, 12),
        fill_rate=round(fill_rate, 8),
        rejection_rate=round(rejection_rate, 8),
        avg_slippage_pct=round(avg_slippage, 8),
        final_position_qty=round(final_position_qty, 12),
        final_position_notional_usd=round(final_position_notional, 8),
        final_flat=final_flat,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        events=[item.model_dump(mode="json") for item in parsed],
        config=resolved_config.model_dump(mode="json"),
    )


def export_testnet_evidence_collection_report(
    report: TestnetEvidenceCollectionReport | dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_evidence_collection_report",
) -> Path:
    config = load_testnet_evidence_collector_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    parsed_report = (
        report
        if isinstance(report, TestnetEvidenceCollectionReport)
        else TestnetEvidenceCollectionReport.model_validate(report)
    )

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(parsed_report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path