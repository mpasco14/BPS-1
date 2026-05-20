from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from execution.live_guard import LiveOrderContext, evaluate_live_order_guard
from ops.live_session_report import (
    LiveSessionEvent,
    build_live_session_report,
    export_live_session_report,
)


load_dotenv()


LiveMicroStatus = Literal["DRY_RUN", "BLOCKED", "READY_FOR_MANUAL_EXECUTION"]


class LiveMicroSessionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    dry_run: bool = True
    output_dir: Path = Path("artifacts/live")
    session_name: str = "live_micro_session"

    max_margin_usd: float = 20.0
    max_notional_usd: float = 600.0
    max_leverage: int = 30
    max_open_positions: int = 1
    allowed_symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT"])

    allow_order_submission: bool = False


class LiveMicroTradeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_name: str = "live_micro_session"
    symbol: str = "BTCUSDT"
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float
    notional_usd: float
    margin_usd: float
    leverage: int

    safety_gate_approved: bool = False
    capital_ramp_approved: bool = False
    live_preflight_passed: bool = False

    binance_allow_live_trading: bool = False
    risk_allow_live_trading: bool = False
    binance_execution_mode: str = "paper"


class LiveMicroSessionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_micro_session"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: LiveMicroStatus
    approved: bool
    submitted: bool = False

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    request: dict[str, Any]
    session_report: dict[str, Any] | None = None


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


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_live_micro_session_config() -> LiveMicroSessionConfig:
    symbols = [
        item.strip().upper()
        for item in os.getenv("LIVE_MICRO_ALLOWED_SYMBOLS", "BTCUSDT").split(",")
        if item.strip()
    ]

    return LiveMicroSessionConfig(
        enabled=env_bool("LIVE_MICRO_SESSION_ENABLED", False),
        dry_run=env_bool("LIVE_MICRO_SESSION_DRY_RUN", True),
        output_dir=Path(os.getenv("LIVE_MICRO_SESSION_OUTPUT_DIR", "artifacts/live")),
        session_name=os.getenv("LIVE_MICRO_SESSION_NAME", "live_micro_session"),
        max_margin_usd=env_float("LIVE_MICRO_MAX_MARGIN_USD", 20),
        max_notional_usd=env_float("LIVE_MICRO_MAX_NOTIONAL_USD", 600),
        max_leverage=env_int("LIVE_MICRO_MAX_LEVERAGE", 30),
        max_open_positions=env_int("LIVE_MICRO_MAX_OPEN_POSITIONS", 1),
        allowed_symbols=symbols,
        allow_order_submission=env_bool("LIVE_MICRO_ALLOW_ORDER_SUBMISSION", False),
    )


def build_live_order_context(request: LiveMicroTradeRequest) -> LiveOrderContext:
    return LiveOrderContext(
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
        price=request.price,
        notional_usd=request.notional_usd,
        margin_usd=request.margin_usd,
        leverage=request.leverage,
        margin_type="ISOLATED",
        binance_allow_live_trading=request.binance_allow_live_trading,
        risk_allow_live_trading=request.risk_allow_live_trading,
        binance_execution_mode=request.binance_execution_mode,
        safety_gate_approved=request.safety_gate_approved,
        capital_ramp_approved=request.capital_ramp_approved,
    )


def run_live_micro_session(
    *,
    request: LiveMicroTradeRequest,
    config: LiveMicroSessionConfig | None = None,
) -> LiveMicroSessionResult:
    resolved_config = config or load_live_micro_session_config()

    blockers: list[str] = []
    warnings: list[str] = []

    if not resolved_config.enabled:
        blockers.append("live_micro_session_disabled")

    if request.symbol.upper() not in resolved_config.allowed_symbols:
        blockers.append("symbol_not_allowed_for_micro_session")

    if request.margin_usd > resolved_config.max_margin_usd:
        blockers.append("micro_margin_above_limit")

    if request.notional_usd > resolved_config.max_notional_usd:
        blockers.append("micro_notional_above_limit")

    if request.leverage > resolved_config.max_leverage:
        blockers.append("micro_leverage_above_limit")

    if not request.live_preflight_passed:
        blockers.append("live_preflight_not_passed")

    guard = evaluate_live_order_guard(
        context=build_live_order_context(request),
    )

    blockers.extend(guard.blockers)
    warnings.extend(guard.warnings)

    if blockers:
        event = LiveSessionEvent(
            session_name=request.session_name,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            notional_usd=request.notional_usd,
            margin_usd=request.margin_usd,
            status="BLOCKED",
            raw={"blockers": blockers},
        )

        report = build_live_session_report(
            session_name=request.session_name,
            events=[event],
            dry_run=True,
            submitted=False,
        )

        return LiveMicroSessionResult(
            status="BLOCKED",
            approved=False,
            submitted=False,
            blockers=blockers,
            warnings=warnings,
            request=request.model_dump(mode="json"),
            session_report=report.model_dump(mode="json"),
        )

    if resolved_config.dry_run or not resolved_config.allow_order_submission:
        event = LiveSessionEvent(
            session_name=request.session_name,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            notional_usd=request.notional_usd,
            margin_usd=request.margin_usd,
            status="PLANNED",
            raw={"dry_run": True},
        )

        report = build_live_session_report(
            session_name=request.session_name,
            events=[event],
            dry_run=True,
            submitted=False,
        )

        return LiveMicroSessionResult(
            status="DRY_RUN",
            approved=True,
            submitted=False,
            warnings=warnings,
            request=request.model_dump(mode="json"),
            session_report=report.model_dump(mode="json"),
        )

    event = LiveSessionEvent(
        session_name=request.session_name,
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
        price=request.price,
        notional_usd=request.notional_usd,
        margin_usd=request.margin_usd,
        status="PLANNED",
        raw={"manual_execution_required": True},
    )

    report = build_live_session_report(
        session_name=request.session_name,
        events=[event],
        dry_run=False,
        submitted=False,
    )

    return LiveMicroSessionResult(
        status="READY_FOR_MANUAL_EXECUTION",
        approved=True,
        submitted=False,
        warnings=["no_live_exchange_adapter_called"],
        request=request.model_dump(mode="json"),
        session_report=report.model_dump(mode="json"),
    )


def export_live_micro_session_result(
    result: LiveMicroSessionResult,
    *,
    output_dir: str | Path | None = None,
    name: str = "live_micro_session_latest",
) -> Path:
    config = load_live_micro_session_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name.replace('/', '_').replace(chr(92), '_')}.json"

    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path