from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from execution.binance_testnet_orders import BinanceTestnetOrderRequest, BinanceTestnetOrdersClient
from execution.testnet_fill_monitor import monitor_order_until_terminal
from execution.testnet_order_guard import (
    TestnetOrderContext,
    TestnetOrderGuardConfig,
    evaluate_testnet_order_guard,
)
from ops.testnet_quality_gate import evaluate_testnet_quality
from ops.testnet_session import (
    TestnetOrderEvent,
    build_testnet_session_report,
    export_testnet_session_report,
)


load_dotenv()


LoopStatus = Literal["APPROVED", "BLOCKED", "DRY_RUN", "SUBMITTED", "FAILED"]


class ControlledTestnetTradeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_name: str = "testnet_controlled_loop"
    symbol: str = "BTCUSDT"
    timeframe: str | None = "5m"

    side: Literal["BUY", "SELL"]
    quantity: float
    price: float
    notional_usd: float

    order_type: str = "LIMIT"
    time_in_force: str = "GTC"

    dry_run: bool = True
    cancel_after_create: bool = True


class ControlledTestnetTradeResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_trading_loop"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: LoopStatus
    approved: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    create_result: dict[str, Any] | None = None
    cancel_result: dict[str, Any] | None = None
    monitor_report: dict[str, Any] | None = None

    session_report: dict[str, Any] | None = None
    quality_report: dict[str, Any] | None = None


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def build_order_context(request: ControlledTestnetTradeRequest) -> TestnetOrderContext:
    return TestnetOrderContext(
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
        notional_usd=request.notional_usd,
        order_type=request.order_type,
        price=request.price,
        testnet_ready=True,
        testnet_allow_order_submission=not request.dry_run,
    )


def build_order_request(request: ControlledTestnetTradeRequest) -> BinanceTestnetOrderRequest:
    return BinanceTestnetOrderRequest(
        symbol=request.symbol,
        side=request.side,
        type=request.order_type,
        timeInForce=request.time_in_force,
        quantity=f"{request.quantity:.3f}",
        price=f"{request.price:.2f}",
    )


def dry_run_event(request: ControlledTestnetTradeRequest) -> TestnetOrderEvent:
    return TestnetOrderEvent(
        session_name=request.session_name,
        symbol=request.symbol,
        timeframe=request.timeframe,
        side=request.side,
        order_type=request.order_type,
        quantity=request.quantity,
        requested_price=request.price,
        executed_price=None,
        status="NEW",
        raw={"dry_run": True},
    )


def run_controlled_testnet_trade(
    *,
    request: ControlledTestnetTradeRequest,
    client: BinanceTestnetOrdersClient | None = None,
) -> ControlledTestnetTradeResult:
    resolved_client = client or BinanceTestnetOrdersClient()

    guard_decision = evaluate_testnet_order_guard(
        context=build_order_context(request),
        config=TestnetOrderGuardConfig(
        require_testnet_ready=not request.dry_run,
        require_submission_flag=not request.dry_run,
    ),
)
    if not guard_decision.approved:
        return ControlledTestnetTradeResult(
            status="BLOCKED",
            approved=False,
            blockers=guard_decision.blockers,
            warnings=guard_decision.warnings,
        )

    if request.dry_run:
        event = dry_run_event(request)
        session_report = build_testnet_session_report(
            events=[event],
            session_name=request.session_name,
        )
        quality = evaluate_testnet_quality(report=session_report)

        return ControlledTestnetTradeResult(
            status="DRY_RUN",
            approved=True,
            warnings=guard_decision.warnings,
            session_report=session_report.model_dump(mode="json"),
            quality_report=quality.model_dump(mode="json"),
        )

    order_request = build_order_request(request)

    create_result = resolved_client.create_order(
        order_request,
        dry_run=False,
        test_order=False,
    )

    cancel_result = None

    if create_result.status == "FAILED":
        return ControlledTestnetTradeResult(
            status="FAILED",
            approved=True,
            warnings=guard_decision.warnings,
            create_result=create_result.model_dump(mode="json"),
        )

    if request.cancel_after_create:
        cancel_result = resolved_client.cancel_order(
            symbol=request.symbol,
            order_id=create_result.order_id,
            client_order_id=create_result.client_order_id,
            dry_run=False,
        )

    monitor = monitor_order_until_terminal(
        client=resolved_client,
        symbol=request.symbol,
        order_id=create_result.order_id,
        client_order_id=create_result.client_order_id,
        session_name=request.session_name,
        timeframe=request.timeframe,
    )

    events = [
        TestnetOrderEvent.model_validate(item)
        for item in monitor.events
    ]

    session_report = build_testnet_session_report(
        events=events,
        session_name=request.session_name,
    )
    quality = evaluate_testnet_quality(report=session_report)

    return ControlledTestnetTradeResult(
        status="SUBMITTED",
        approved=True,
        warnings=guard_decision.warnings,
        create_result=create_result.model_dump(mode="json"),
        cancel_result=cancel_result.model_dump(mode="json") if cancel_result else None,
        monitor_report=monitor.model_dump(mode="json"),
        session_report=session_report.model_dump(mode="json"),
        quality_report=quality.model_dump(mode="json"),
    )


def export_controlled_testnet_trade_result(
    result: ControlledTestnetTradeResult,
    *,
    output_dir: str | Path = "artifacts/testnet",
    name: str = "controlled_testnet_trade_latest",
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def export_result_session_files(
    result: ControlledTestnetTradeResult,
    *,
    output_dir: str | Path = "artifacts/testnet",
    name: str = "controlled_testnet_trade",
) -> dict[str, Path] | None:
    if not result.session_report:
        return None

    session = build_testnet_session_report(
        events=result.session_report.get("events", []),
        session_name=result.session_report.get("session_name", name),
    )

    return export_testnet_session_report(
        session,
        output_dir=output_dir,
        name=name,
    )