from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.signed_client import (
    BinanceTestnetAdapterConfig,
    BinanceTestnetSignedClient,
    build_binance_testnet_signed_client,
    load_binance_testnet_adapter_config,
)


OrderSubmitStatus = Literal["DRY_RUN", "VALIDATED", "SUBMITTED", "BLOCKED", "ERROR"]
OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]


class BinanceTestnetOrderSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    side: OrderSide = "BUY"
    order_type: OrderType = "LIMIT"

    quantity: float
    price: float | None = None
    time_in_force: str = "GTC"

    reduce_only: bool = False
    dry_run: bool = True
    validate_on_exchange: bool = False

    new_client_order_id: str = Field(default_factory=lambda: f"testnet_{uuid4().hex[:24]}")

    metadata: dict[str, Any] = Field(default_factory=dict)


class BinanceTestnetOrderSubmitReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_testnet_order_submit_adapter"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: OrderSubmitStatus
    passed: bool
    submitted: bool
    dry_run: bool
    simulated: bool

    request: dict[str, Any]
    endpoint: str | None = None
    response: dict[str, Any] | None = None

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    config: dict[str, Any]


def validate_order_submit_request(request: BinanceTestnetOrderSubmitRequest) -> list[str]:
    blockers: list[str] = []

    if request.quantity <= 0:
        blockers.append("quantity_must_be_positive")

    if request.order_type == "LIMIT":
        if request.price is None:
            blockers.append("price_required_for_limit_order")
        elif request.price <= 0:
            blockers.append("price_must_be_positive")

        if not request.time_in_force:
            blockers.append("time_in_force_required_for_limit_order")

    if len(request.new_client_order_id) > 36:
        blockers.append("new_client_order_id_too_long")

    return blockers


def build_order_params(request: BinanceTestnetOrderSubmitRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "symbol": request.symbol,
        "side": request.side,
        "type": request.order_type,
        "quantity": request.quantity,
        "newClientOrderId": request.new_client_order_id,
        "newOrderRespType": "ACK",
    }

    if request.order_type == "LIMIT":
        params["timeInForce"] = request.time_in_force
        params["price"] = request.price

    if request.reduce_only:
        params["reduceOnly"] = "true"

    return params


def submit_binance_testnet_order(
    *,
    request: BinanceTestnetOrderSubmitRequest | dict[str, Any],
    client: BinanceTestnetSignedClient | None = None,
    config: BinanceTestnetAdapterConfig | None = None,
) -> BinanceTestnetOrderSubmitReport:
    parsed_request = (
        request
        if isinstance(request, BinanceTestnetOrderSubmitRequest)
        else BinanceTestnetOrderSubmitRequest.model_validate(request)
    )
    resolved_config = config or load_binance_testnet_adapter_config()
    resolved_client = client or build_binance_testnet_signed_client(config=resolved_config)

    blockers = validate_order_submit_request(parsed_request)
    warnings: list[str] = []

    if blockers:
        return BinanceTestnetOrderSubmitReport(
            status="BLOCKED",
            passed=False,
            submitted=False,
            dry_run=parsed_request.dry_run,
            simulated=resolved_config.simulate,
            request=parsed_request.model_dump(mode="json"),
            blockers=blockers,
            warnings=warnings,
            config=resolved_config.model_dump(mode="json"),
        )

    params = build_order_params(parsed_request)

    if parsed_request.dry_run and not parsed_request.validate_on_exchange:
        return BinanceTestnetOrderSubmitReport(
            status="DRY_RUN",
            passed=True,
            submitted=False,
            dry_run=True,
            simulated=True,
            request=parsed_request.model_dump(mode="json"),
            endpoint=None,
            response={"dry_run": True, "params": params},
            warnings=["order_not_sent_dry_run"],
            config=resolved_config.model_dump(mode="json"),
        )

    if parsed_request.dry_run and parsed_request.validate_on_exchange:
        response = resolved_client.request(
            method="POST",
            path="/fapi/v1/order/test",
            params=params,
            signed=True,
            simulate_data={"validated": True, "params": params},
        )

        return BinanceTestnetOrderSubmitReport(
            status="VALIDATED" if response.ok else "ERROR",
            passed=response.ok,
            submitted=False,
            dry_run=True,
            simulated=response.simulated,
            request=parsed_request.model_dump(mode="json"),
            endpoint="/fapi/v1/order/test",
            response=response.model_dump(mode="json"),
            blockers=[] if response.ok else ["test_order_validation_failed"],
            warnings=["test_order_validation_only_no_matching_engine_submission"],
            config=resolved_config.model_dump(mode="json"),
        )

    if not resolved_config.allow_order_submission:
        return BinanceTestnetOrderSubmitReport(
            status="BLOCKED",
            passed=False,
            submitted=False,
            dry_run=False,
            simulated=resolved_config.simulate,
            request=parsed_request.model_dump(mode="json"),
            endpoint="/fapi/v1/order",
            blockers=["testnet_order_submission_not_allowed"],
            warnings=["enable_BINANCE_TESTNET_ALLOW_ORDER_SUBMISSION_only_for_supervised_testnet"],
            config=resolved_config.model_dump(mode="json"),
        )

    response = resolved_client.request(
        method="POST",
        path="/fapi/v1/order",
        params=params,
        signed=True,
        simulate_data={
            "symbol": parsed_request.symbol,
            "orderId": 123456,
            "clientOrderId": parsed_request.new_client_order_id,
            "status": "NEW",
            "side": parsed_request.side,
            "type": parsed_request.order_type,
            "origQty": str(parsed_request.quantity),
            "price": str(parsed_request.price or 0),
        },
    )

    return BinanceTestnetOrderSubmitReport(
        status="SUBMITTED" if response.ok else "ERROR",
        passed=response.ok,
        submitted=response.ok,
        dry_run=False,
        simulated=response.simulated,
        request=parsed_request.model_dump(mode="json"),
        endpoint="/fapi/v1/order",
        response=response.model_dump(mode="json"),
        blockers=[] if response.ok else ["order_submission_failed"],
        warnings=warnings,
        config=resolved_config.model_dump(mode="json"),
    )


def export_binance_testnet_order_submit_report(
    report: BinanceTestnetOrderSubmitReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "binance_testnet_order_submit",
) -> Path:
    path = Path(output_dir or os.getenv("BINANCE_TESTNET_ORDER_OUTPUT_DIR", "artifacts/binance_testnet_adapter"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path