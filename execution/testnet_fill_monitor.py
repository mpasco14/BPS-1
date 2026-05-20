from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from execution.binance_testnet_orders import BinanceTestnetOrderResult, BinanceTestnetOrdersClient
from ops.testnet_session import TestnetOrderEvent


load_dotenv()


class TestnetFillMonitorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_polls: int = 5
    poll_interval_seconds: float = 1.0
    terminal_statuses: list[str] = Field(
        default_factory=lambda: ["FILLED", "CANCELED", "REJECTED", "EXPIRED"]
    )


class TestnetFillMonitorReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_fill_monitor"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    symbol: str
    order_id: str | int | None = None
    client_order_id: str | None = None

    terminal: bool
    polls: int
    final_status: str | None = None

    events: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_testnet_fill_monitor_config() -> TestnetFillMonitorConfig:
    terminal_statuses = [
        item.strip().upper()
        for item in os.getenv(
            "TESTNET_FILL_MONITOR_TERMINAL_STATUSES",
            "FILLED,CANCELED,REJECTED,EXPIRED",
        ).split(",")
        if item.strip()
    ]

    return TestnetFillMonitorConfig(
        max_polls=env_int("TESTNET_FILL_MONITOR_MAX_POLLS", 5),
        poll_interval_seconds=env_float("TESTNET_FILL_MONITOR_POLL_INTERVAL_SECONDS", 1),
        terminal_statuses=terminal_statuses,
    )


def normalize_status(status: str | None) -> str:
    return (status or "NEW").upper()


def order_result_to_event(
    result: BinanceTestnetOrderResult,
    *,
    session_name: str,
    timeframe: str | None = None,
) -> TestnetOrderEvent:
    payload = result.response or {}

    quantity = float(payload.get("origQty") or payload.get("executedQty") or 0)
    requested_price = payload.get("price")
    executed_price = payload.get("avgPrice") or payload.get("price")

    return TestnetOrderEvent(
        session_name=session_name,
        symbol=result.symbol,
        timeframe=timeframe,
        side=payload.get("side") or "BUY",
        order_type=payload.get("type") or "LIMIT",
        quantity=quantity,
        requested_price=float(requested_price) if requested_price not in {None, ""} else None,
        executed_price=float(executed_price) if executed_price not in {None, ""} else None,
        status=normalize_status(result.order_status),  # type: ignore[arg-type]
        order_id=result.order_id,
        client_order_id=result.client_order_id,
        latency_ms=result.latency_ms,
        raw=result.model_dump(mode="json"),
    )


def parse_order_trade_update(
    payload: dict[str, Any],
    *,
    session_name: str,
    timeframe: str | None = None,
) -> TestnetOrderEvent:
    order = payload.get("o") or {}

    symbol = order.get("s") or "BTCUSDT"
    side = order.get("S") or "BUY"
    order_type = order.get("o") or "LIMIT"
    quantity = float(order.get("q") or 0)

    requested_price = order.get("p")
    last_executed_price = order.get("L")
    average_price = order.get("ap")

    status = order.get("X") or "NEW"

    return TestnetOrderEvent(
        session_name=session_name,
        symbol=symbol,
        timeframe=timeframe,
        side=side,
        order_type=order_type,
        quantity=quantity,
        requested_price=float(requested_price) if requested_price not in {None, "", "0"} else None,
        executed_price=float(average_price or last_executed_price) if (average_price or last_executed_price) not in {None, "", "0"} else None,
        status=normalize_status(status),  # type: ignore[arg-type]
        order_id=order.get("i"),
        client_order_id=order.get("c"),
        fee_usd=float(order.get("n") or 0),
        raw=payload,
    )


def monitor_order_until_terminal(
    *,
    client: BinanceTestnetOrdersClient,
    symbol: str,
    order_id: str | int | None = None,
    client_order_id: str | None = None,
    session_name: str = "testnet_session",
    timeframe: str | None = None,
    config: TestnetFillMonitorConfig | None = None,
) -> TestnetFillMonitorReport:
    resolved_config = config or load_testnet_fill_monitor_config()

    events: list[TestnetOrderEvent] = []
    errors: list[str] = []
    final_status: str | None = None

    for poll_index in range(resolved_config.max_polls):
        result = client.query_order(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
        )

        if result.status == "FAILED":
            errors.append(result.error or "query_failed")
        else:
            event = order_result_to_event(
                result,
                session_name=session_name,
                timeframe=timeframe,
            )
            events.append(event)
            final_status = normalize_status(result.order_status)

            if final_status in resolved_config.terminal_statuses:
                return TestnetFillMonitorReport(
                    symbol=symbol,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    terminal=True,
                    polls=poll_index + 1,
                    final_status=final_status,
                    events=[item.model_dump(mode="json") for item in events],
                    errors=errors,
                )

        if resolved_config.poll_interval_seconds > 0:
            time.sleep(resolved_config.poll_interval_seconds)

    return TestnetFillMonitorReport(
        symbol=symbol,
        order_id=order_id,
        client_order_id=client_order_id,
        terminal=False,
        polls=resolved_config.max_polls,
        final_status=final_status,
        events=[item.model_dump(mode="json") for item in events],
        errors=errors,
    )