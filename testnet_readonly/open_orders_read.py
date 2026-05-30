from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from binance_testnet_adapter.sanitization import sanitize_artifact_payload
from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.signed_client import (
    BinanceTestnetAdapterConfig,
    BinanceTestnetSignedClient,
    build_binance_testnet_signed_client,
    load_binance_testnet_adapter_config,
)


OpenOrdersReadStatus = Literal["PASS", "WARN", "FAIL"]


class BinanceTestnetOpenOrderSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    order_id: int | None = None
    client_order_id: str | None = None
    side: str | None = None
    order_type: str | None = None
    status: str | None = None
    price: float = 0.0
    orig_qty: float = 0.0
    executed_qty: float = 0.0
    reduce_only: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class RealOpenOrdersReadReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "real_testnet_open_orders_read"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: OpenOrdersReadStatus
    passed: bool
    simulated: bool

    symbol: str
    open_orders_count: int
    allow_open_orders: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    open_orders: list[dict[str, Any]] = Field(default_factory=list)
    raw_response: Any = None
    response: dict[str, Any] | None = None
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_open_orders(payload: Any) -> list[BinanceTestnetOpenOrderSnapshot]:
    if not isinstance(payload, list):
        return []

    orders: list[BinanceTestnetOpenOrderSnapshot] = []

    for item in payload:
        if not isinstance(item, dict):
            continue

        orders.append(
            BinanceTestnetOpenOrderSnapshot(
                symbol=item.get("symbol", "BTCUSDT"),
                order_id=item.get("orderId"),
                client_order_id=item.get("clientOrderId"),
                side=item.get("side"),
                order_type=item.get("type") or item.get("origType"),
                status=item.get("status"),
                price=to_float(item.get("price")),
                orig_qty=to_float(item.get("origQty")),
                executed_qty=to_float(item.get("executedQty")),
                reduce_only=bool(item.get("reduceOnly", False)),
                raw=item,
            )
        )

    return orders


def simulated_open_orders_payload() -> list[dict[str, Any]]:
    return []


def read_real_testnet_open_orders(
    *,
    symbol: str = "BTCUSDT",
    client: BinanceTestnetSignedClient | None = None,
    adapter_config: BinanceTestnetAdapterConfig | None = None,
    allow_open_orders: bool | None = None,
) -> RealOpenOrdersReadReport:
    resolved_config = adapter_config or load_binance_testnet_adapter_config()
    resolved_client = client or build_binance_testnet_signed_client(config=resolved_config)
    resolved_allow_open_orders = (
        env_bool("TESTNET_READONLY_ALLOW_OPEN_ORDERS", False)
        if allow_open_orders is None
        else allow_open_orders
    )

    response = resolved_client.request(
        method="GET",
        path="/fapi/v1/openOrders",
        params={"symbol": symbol},
        signed=True,
        simulate_data=simulated_open_orders_payload(),
    )

    blockers: list[str] = []
    warnings: list[str] = []

    if not response.ok:
        blockers.append("open_orders_request_failed")
        if response.error_message:
            warnings.append(response.error_message)

    orders = parse_open_orders(response.data)

    if orders and not resolved_allow_open_orders:
        blockers.append("open_orders_detected_during_readonly_validation")

    if orders:
        warnings.append("open_orders_present")

    passed = not blockers

    return RealOpenOrdersReadReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        simulated=response.simulated,
        symbol=symbol,
        open_orders_count=len(orders),
        allow_open_orders=resolved_allow_open_orders,
        blockers=blockers,
        warnings=sorted(set(warnings)),
        open_orders=[item.model_dump(mode="json") for item in orders],
        raw_response=response.data,
        response=response.model_dump(mode="json"),
        config=sanitize_artifact_payload(resolved_config.model_dump(mode="json"))       
    )


def export_real_testnet_open_orders_read_report(
    report: RealOpenOrdersReadReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_open_orders_read",
) -> Path:
    path = Path(output_dir or os.getenv("TESTNET_READONLY_OPEN_ORDERS_OUTPUT_DIR", "artifacts/testnet_readonly"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path