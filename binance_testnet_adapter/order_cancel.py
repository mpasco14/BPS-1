from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.signed_client import (
    BinanceTestnetAdapterConfig,
    BinanceTestnetSignedClient,
    build_binance_testnet_signed_client,
    load_binance_testnet_adapter_config,
)


CancelStatus = Literal["CANCELED", "OPEN_ORDER_FOUND", "NOT_FOUND", "BLOCKED", "ERROR", "SIMULATED"]


class BinanceTestnetCancelOrderRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    order_id: int | None = None
    orig_client_order_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BinanceTestnetOrderQueryReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_testnet_open_order_query_adapter"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: CancelStatus
    passed: bool
    simulated: bool

    request: dict[str, Any]
    response: dict[str, Any] | None = None

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    config: dict[str, Any]


class BinanceTestnetCancelOrderReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_testnet_cancel_order_adapter"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: CancelStatus
    passed: bool
    canceled: bool
    simulated: bool

    request: dict[str, Any]
    response: dict[str, Any] | None = None

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    config: dict[str, Any]


def validate_cancel_request(request: BinanceTestnetCancelOrderRequest) -> list[str]:
    blockers: list[str] = []

    if not request.order_id and not request.orig_client_order_id:
        blockers.append("order_id_or_orig_client_order_id_required")

    return blockers


def cancel_request_params(request: BinanceTestnetCancelOrderRequest) -> dict[str, Any]:
    params: dict[str, Any] = {"symbol": request.symbol}

    if request.order_id is not None:
        params["orderId"] = request.order_id

    if request.orig_client_order_id:
        params["origClientOrderId"] = request.orig_client_order_id

    return params


def query_binance_testnet_open_order(
    *,
    request: BinanceTestnetCancelOrderRequest | dict[str, Any],
    client: BinanceTestnetSignedClient | None = None,
    config: BinanceTestnetAdapterConfig | None = None,
) -> BinanceTestnetOrderQueryReport:
    parsed_request = (
        request
        if isinstance(request, BinanceTestnetCancelOrderRequest)
        else BinanceTestnetCancelOrderRequest.model_validate(request)
    )
    resolved_config = config or load_binance_testnet_adapter_config()
    resolved_client = client or build_binance_testnet_signed_client(config=resolved_config)

    blockers = validate_cancel_request(parsed_request)

    if blockers:
        return BinanceTestnetOrderQueryReport(
            status="BLOCKED",
            passed=False,
            simulated=resolved_config.simulate,
            request=parsed_request.model_dump(mode="json"),
            blockers=blockers,
            config=resolved_config.model_dump(mode="json"),
        )

    response = resolved_client.request(
        method="GET",
        path="/fapi/v1/openOrder",
        params=cancel_request_params(parsed_request),
        signed=True,
        simulate_data={
            "symbol": parsed_request.symbol,
            "orderId": parsed_request.order_id or 123456,
            "clientOrderId": parsed_request.orig_client_order_id or "simulated_order",
            "status": "NEW",
        },
    )

    return BinanceTestnetOrderQueryReport(
        status="OPEN_ORDER_FOUND" if response.ok else "ERROR",
        passed=response.ok,
        simulated=response.simulated,
        request=parsed_request.model_dump(mode="json"),
        response=response.model_dump(mode="json"),
        blockers=[] if response.ok else ["open_order_query_failed"],
        warnings=[],
        config=resolved_config.model_dump(mode="json"),
    )


def cancel_binance_testnet_order(
    *,
    request: BinanceTestnetCancelOrderRequest | dict[str, Any],
    client: BinanceTestnetSignedClient | None = None,
    config: BinanceTestnetAdapterConfig | None = None,
) -> BinanceTestnetCancelOrderReport:
    parsed_request = (
        request
        if isinstance(request, BinanceTestnetCancelOrderRequest)
        else BinanceTestnetCancelOrderRequest.model_validate(request)
    )
    resolved_config = config or load_binance_testnet_adapter_config()
    resolved_client = client or build_binance_testnet_signed_client(config=resolved_config)

    blockers = validate_cancel_request(parsed_request)

    if blockers:
        return BinanceTestnetCancelOrderReport(
            status="BLOCKED",
            passed=False,
            canceled=False,
            simulated=resolved_config.simulate,
            request=parsed_request.model_dump(mode="json"),
            blockers=blockers,
            config=resolved_config.model_dump(mode="json"),
        )

    if not resolved_config.allow_cancel_orders:
        return BinanceTestnetCancelOrderReport(
            status="BLOCKED",
            passed=False,
            canceled=False,
            simulated=resolved_config.simulate,
            request=parsed_request.model_dump(mode="json"),
            blockers=["testnet_cancel_orders_not_allowed"],
            warnings=["enable_BINANCE_TESTNET_ALLOW_CANCEL_ORDERS_only_for_supervised_testnet"],
            config=resolved_config.model_dump(mode="json"),
        )

    response = resolved_client.request(
        method="DELETE",
        path="/fapi/v1/order",
        params=cancel_request_params(parsed_request),
        signed=True,
        simulate_data={
            "symbol": parsed_request.symbol,
            "orderId": parsed_request.order_id or 123456,
            "clientOrderId": parsed_request.orig_client_order_id or "simulated_order",
            "status": "CANCELED",
        },
    )

    return BinanceTestnetCancelOrderReport(
        status="CANCELED" if response.ok else "ERROR",
        passed=response.ok,
        canceled=response.ok,
        simulated=response.simulated,
        request=parsed_request.model_dump(mode="json"),
        response=response.model_dump(mode="json"),
        blockers=[] if response.ok else ["cancel_order_failed"],
        warnings=[],
        config=resolved_config.model_dump(mode="json"),
    )


def export_binance_testnet_cancel_order_report(
    report: BinanceTestnetCancelOrderReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "binance_testnet_cancel_order",
) -> Path:
    path = Path(output_dir or os.getenv("BINANCE_TESTNET_CANCEL_OUTPUT_DIR", "artifacts/binance_testnet_adapter"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path