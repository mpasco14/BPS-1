from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.order_cancel import BinanceTestnetCancelOrderReport, BinanceTestnetOrderQueryReport
from binance_testnet_adapter.order_submit import BinanceTestnetOrderSubmitReport
from testnet_order_lifecycle.lifecycle_models import export_lifecycle_json


FillCaptureStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetFillRejectionCaptureReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "real_testnet_fill_rejection_capture"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: FillCaptureStatus
    passed: bool
    simulated: bool

    fill_detected: bool = False
    rejection_detected: bool = False
    cancel_detected: bool = False

    submitted: bool = False
    order_status: str | None = None

    filled_qty: float = 0.0
    requested_qty: float = 0.0
    fill_rate: float = 0.0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    submit: dict[str, Any] | None = None
    query: dict[str, Any] | None = None
    cancel: dict[str, Any] | None = None


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_order_status(response_payload: Any) -> str | None:
    if not isinstance(response_payload, dict):
        return None

    data = response_payload.get("data")
    if isinstance(data, dict):
        return data.get("status")

    response = response_payload.get("response")
    if isinstance(response, dict):
        nested = response.get("data")
        if isinstance(nested, dict):
            return nested.get("status")

    return response_payload.get("status")


def capture_testnet_fill_rejection(
    *,
    submit: BinanceTestnetOrderSubmitReport | dict[str, Any] | None = None,
    query: BinanceTestnetOrderQueryReport | dict[str, Any] | None = None,
    cancel: BinanceTestnetCancelOrderReport | dict[str, Any] | None = None,
) -> TestnetFillRejectionCaptureReport:
    parsed_submit = (
        submit
        if isinstance(submit, BinanceTestnetOrderSubmitReport)
        else BinanceTestnetOrderSubmitReport.model_validate(submit)
        if submit is not None
        else None
    )
    parsed_query = (
        query
        if isinstance(query, BinanceTestnetOrderQueryReport)
        else BinanceTestnetOrderQueryReport.model_validate(query)
        if query is not None
        else None
    )
    parsed_cancel = (
        cancel
        if isinstance(cancel, BinanceTestnetCancelOrderReport)
        else BinanceTestnetCancelOrderReport.model_validate(cancel)
        if cancel is not None
        else None
    )

    blockers: list[str] = []
    warnings: list[str] = []

    submitted = bool(parsed_submit and parsed_submit.submitted)
    simulated = bool(
        (parsed_submit and parsed_submit.simulated)
        or (parsed_query and parsed_query.simulated)
        or (parsed_cancel and parsed_cancel.simulated)
    )

    statuses = []

    if parsed_submit and parsed_submit.response:
        status = extract_order_status(parsed_submit.response)
        if status:
            statuses.append(status)

    if parsed_query and parsed_query.response:
        status = extract_order_status(parsed_query.response)
        if status:
            statuses.append(status)

    if parsed_cancel and parsed_cancel.response:
        status = extract_order_status(parsed_cancel.response)
        if status:
            statuses.append(status)

    order_status = statuses[-1] if statuses else None

    fill_detected = order_status in {"FILLED", "PARTIALLY_FILLED"}
    rejection_detected = bool(parsed_submit and parsed_submit.status == "ERROR")
    cancel_detected = bool(parsed_cancel and parsed_cancel.canceled)

    requested_qty = 0.0
    filled_qty = 0.0

    if parsed_submit:
        request_payload = parsed_submit.request or {}
        requested_qty = to_float(request_payload.get("quantity"))

    if fill_detected:
        filled_qty = requested_qty

    fill_rate = filled_qty / requested_qty if requested_qty > 0 else 0.0

    if rejection_detected:
        blockers.append("order_rejection_detected")

    if submitted and not fill_detected and not cancel_detected:
        warnings.append("order_submitted_without_fill_or_cancel_confirmation")

    passed = not blockers

    return TestnetFillRejectionCaptureReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        simulated=simulated,
        fill_detected=fill_detected,
        rejection_detected=rejection_detected,
        cancel_detected=cancel_detected,
        submitted=submitted,
        order_status=order_status,
        filled_qty=round(filled_qty, 12),
        requested_qty=round(requested_qty, 12),
        fill_rate=round(fill_rate, 8),
        blockers=blockers,
        warnings=warnings,
        submit=parsed_submit.model_dump(mode="json") if parsed_submit else None,
        query=parsed_query.model_dump(mode="json") if parsed_query else None,
        cancel=parsed_cancel.model_dump(mode="json") if parsed_cancel else None,
    )


def export_fill_rejection_capture_report(
    report: TestnetFillRejectionCaptureReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_fill_rejection_capture",
) -> Path:
    return export_lifecycle_json(
        report,
        output_dir=output_dir or os.getenv("TESTNET_ORDER_LIFECYCLE_FILL_OUTPUT_DIR", "artifacts/testnet_order_lifecycle"),
        name=name,
    )