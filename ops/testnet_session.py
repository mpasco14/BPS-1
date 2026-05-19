"""
Testnet session recorder.

Responsabilidades:
- Registrar eventos de ordens em testnet.
- Calcular métricas de qualidade da execução.
- Exportar relatório JSON e eventos JSONL.
- Não envia ordens.
- Não habilita live trading.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


OrderEventStatus = Literal["NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"]


class TestnetSessionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet")
    default_name: str = "testnet_session"


class TestnetOrderEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str = "testnet_session"
    symbol: str = "BTCUSDT"
    timeframe: str | None = None

    side: str
    order_type: str = "LIMIT"

    quantity: float
    requested_price: float | None = None
    executed_price: float | None = None

    status: OrderEventStatus

    order_id: str | int | None = None
    client_order_id: str | None = None

    latency_ms: float | None = None
    estimated_slippage_pct: float | None = None
    realized_slippage_pct: float | None = None

    fee_usd: float = 0.0
    pnl_usd: float = 0.0

    rejection_reason: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class TestnetSessionMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    events_total: int = 0

    new_orders: int = 0
    filled_orders: int = 0
    partial_fills: int = 0
    canceled_orders: int = 0
    rejected_orders: int = 0
    expired_orders: int = 0

    fill_rate: float = 0.0
    rejection_rate: float = 0.0
    cancel_rate: float = 0.0

    average_latency_ms: float | None = None
    average_slippage_error_pct: float | None = None

    gross_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    net_pnl_usd: float = 0.0


class TestnetSessionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_session"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str
    started_at: datetime | None = None
    ended_at: datetime | None = None

    metrics: dict[str, Any]
    events: list[dict[str, Any]] = Field(default_factory=list)


def load_testnet_session_config() -> TestnetSessionConfig:
    return TestnetSessionConfig(
        output_dir=Path(os.getenv("TESTNET_SESSION_OUTPUT_DIR", "artifacts/testnet")),
        default_name=os.getenv("TESTNET_SESSION_DEFAULT_NAME", "testnet_session"),
    )


def calculate_slippage_error_pct(event: TestnetOrderEvent) -> float | None:
    if event.estimated_slippage_pct is None or event.realized_slippage_pct is None:
        return None

    return abs(float(event.realized_slippage_pct) - float(event.estimated_slippage_pct))


def average(values: list[float]) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


def build_testnet_session_metrics(events: list[TestnetOrderEvent]) -> TestnetSessionMetrics:
    events_total = len(events)

    if events_total == 0:
        return TestnetSessionMetrics()

    new_orders = sum(1 for event in events if event.status == "NEW")
    filled_orders = sum(1 for event in events if event.status == "FILLED")
    partial_fills = sum(1 for event in events if event.status == "PARTIALLY_FILLED")
    canceled_orders = sum(1 for event in events if event.status == "CANCELED")
    rejected_orders = sum(1 for event in events if event.status == "REJECTED")
    expired_orders = sum(1 for event in events if event.status == "EXPIRED")

    terminal_orders = filled_orders + canceled_orders + rejected_orders + expired_orders

    fill_rate = filled_orders / terminal_orders if terminal_orders else 0.0
    rejection_rate = rejected_orders / terminal_orders if terminal_orders else 0.0
    cancel_rate = canceled_orders / terminal_orders if terminal_orders else 0.0

    latencies = [
        float(event.latency_ms)
        for event in events
        if event.latency_ms is not None
    ]

    slippage_errors = [
        value
        for value in [calculate_slippage_error_pct(event) for event in events]
        if value is not None
    ]

    gross_pnl = sum(float(event.pnl_usd) for event in events)
    fees = sum(float(event.fee_usd) for event in events)

    return TestnetSessionMetrics(
        events_total=events_total,
        new_orders=new_orders,
        filled_orders=filled_orders,
        partial_fills=partial_fills,
        canceled_orders=canceled_orders,
        rejected_orders=rejected_orders,
        expired_orders=expired_orders,
        fill_rate=fill_rate,
        rejection_rate=rejection_rate,
        cancel_rate=cancel_rate,
        average_latency_ms=average(latencies),
        average_slippage_error_pct=average(slippage_errors),
        gross_pnl_usd=gross_pnl,
        fees_usd=fees,
        net_pnl_usd=gross_pnl - fees,
    )


def build_testnet_session_report(
    *,
    events: list[TestnetOrderEvent | dict[str, Any]],
    session_name: str,
) -> TestnetSessionReport:
    parsed_events = [
        event if isinstance(event, TestnetOrderEvent) else TestnetOrderEvent.model_validate(event)
        for event in events
    ]

    metrics = build_testnet_session_metrics(parsed_events)

    started_at = min((event.timestamp for event in parsed_events), default=None)
    ended_at = max((event.timestamp for event in parsed_events), default=None)

    return TestnetSessionReport(
        session_name=session_name,
        started_at=started_at,
        ended_at=ended_at,
        metrics=metrics.model_dump(mode="json"),
        events=[event.model_dump(mode="json") for event in parsed_events],
    )


def export_testnet_session_report(
    report: TestnetSessionReport,
    *,
    output_dir: str | Path | None = None,
    name: str | None = None,
) -> dict[str, Path]:
    config = load_testnet_session_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = (name or report.session_name).replace("/", "_").replace("\\", "_")

    summary_path = resolved_output_dir / f"{safe_name}_summary.json"
    events_path = resolved_output_dir / f"{safe_name}_events.jsonl"

    summary_payload = report.model_dump(mode="json")
    summary_payload.pop("events", None)

    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with events_path.open("w", encoding="utf-8") as file:
        for event in report.events:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    return {
        "summary": summary_path,
        "events": events_path,
    }


def load_testnet_events_jsonl(path: str | Path) -> list[TestnetOrderEvent]:
    input_path = Path(path)

    if not input_path.exists():
        return []

    events: list[TestnetOrderEvent] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            events.append(TestnetOrderEvent.model_validate(json.loads(line)))

    return events