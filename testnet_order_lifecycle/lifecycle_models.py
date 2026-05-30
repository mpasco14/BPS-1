from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()

__test__ = False


LifecycleStatus = Literal["PASS", "WARN", "FAIL", "BLOCKED"]
LifecycleEventType = Literal[
    "TEST_ORDER_VALIDATED",
    "TEST_ORDER_FAILED",
    "ORDER_SUBMIT_DRY_RUN",
    "ORDER_SUBMITTED",
    "ORDER_SUBMIT_BLOCKED",
    "ORDER_SUBMIT_FAILED",
    "OPEN_ORDER_FOUND",
    "OPEN_ORDER_NOT_FOUND",
    "ORDER_CANCELED",
    "ORDER_CANCEL_BLOCKED",
    "ORDER_CANCEL_FAILED",
    "FILL_DETECTED",
    "REJECTION_DETECTED",
    "POSITION_RECONCILED",
    "FINAL_REPORT",
]


class TestnetOrderLifecycleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_order_lifecycle")

    symbol: str = "BTCUSDT"
    side: Literal["BUY", "SELL"] = "BUY"
    quantity: float = 0.001
    price: float = 60000.0
    time_in_force: str = "GTC"

    simulate: bool = True
    allow_real_submit: bool = False
    allow_real_cancel: bool = False

    require_test_order_pass: bool = True
    require_cancel_attempt: bool = True
    require_final_flat: bool = True
    require_no_live_flags: bool = True

    max_notional_usd: float = 100.0
    max_qty: float = 0.001
    max_rejection_count: int = 0
    max_slippage_pct: float = 0.005


class TestnetOrderLifecycleEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str = Field(default_factory=lambda: f"life_{uuid4().hex}")
    event_type: LifecycleEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    symbol: str = "BTCUSDT"
    order_id: int | None = None
    client_order_id: str | None = None

    status: str | None = None
    passed: bool = True

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    payload: dict[str, Any] = Field(default_factory=dict)


class TestnetOrderLifecycleReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "real_testnet_order_lifecycle_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: LifecycleStatus
    passed: bool
    simulated: bool

    symbol: str
    client_order_id: str | None = None
    order_id: int | None = None

    test_order_passed: bool = False
    submit_passed: bool = False
    submitted: bool = False
    open_order_query_passed: bool = False
    cancel_attempted: bool = False
    cancel_passed: bool = False
    fill_detected: bool = False
    rejection_detected: bool = False
    final_flat: bool = False

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    events: list[dict[str, Any]] = Field(default_factory=list)

    test_order: dict[str, Any] | None = None
    submit: dict[str, Any] | None = None
    open_order_query: dict[str, Any] | None = None
    cancel: dict[str, Any] | None = None
    fill_capture: dict[str, Any] | None = None
    position_reconciliation: dict[str, Any] | None = None

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


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_testnet_order_lifecycle_config() -> TestnetOrderLifecycleConfig:
    return TestnetOrderLifecycleConfig(
        output_dir=Path(os.getenv("TESTNET_ORDER_LIFECYCLE_OUTPUT_DIR", "artifacts/testnet_order_lifecycle")),
        symbol=os.getenv("TESTNET_ORDER_LIFECYCLE_SYMBOL", "BTCUSDT"),
        side=os.getenv("TESTNET_ORDER_LIFECYCLE_SIDE", "BUY"),
        quantity=env_float("TESTNET_ORDER_LIFECYCLE_QUANTITY", 0.001),
        price=env_float("TESTNET_ORDER_LIFECYCLE_PRICE", 60000),
        time_in_force=os.getenv("TESTNET_ORDER_LIFECYCLE_TIME_IN_FORCE", "GTC"),
        simulate=env_bool("TESTNET_ORDER_LIFECYCLE_SIMULATE", True),
        allow_real_submit=env_bool("TESTNET_ORDER_LIFECYCLE_ALLOW_REAL_SUBMIT", False),
        allow_real_cancel=env_bool("TESTNET_ORDER_LIFECYCLE_ALLOW_REAL_CANCEL", False),
        require_test_order_pass=env_bool("TESTNET_ORDER_LIFECYCLE_REQUIRE_TEST_ORDER_PASS", True),
        require_cancel_attempt=env_bool("TESTNET_ORDER_LIFECYCLE_REQUIRE_CANCEL_ATTEMPT", True),
        require_final_flat=env_bool("TESTNET_ORDER_LIFECYCLE_REQUIRE_FINAL_FLAT", True),
        require_no_live_flags=env_bool("TESTNET_ORDER_LIFECYCLE_REQUIRE_NO_LIVE_FLAGS", True),
        max_notional_usd=env_float("TESTNET_ORDER_LIFECYCLE_MAX_NOTIONAL_USD", 100),
        max_qty=env_float("TESTNET_ORDER_LIFECYCLE_MAX_QTY", 0.001),
        max_rejection_count=env_int("TESTNET_ORDER_LIFECYCLE_MAX_REJECTION_COUNT", 0),
        max_slippage_pct=env_float("TESTNET_ORDER_LIFECYCLE_MAX_SLIPPAGE_PCT", 0.005),
    )


def live_flags_detected() -> bool:
    return any(
        [
            env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
            env_bool("RISK_ALLOW_LIVE_TRADING", False),
            env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
        ]
    )


def validate_lifecycle_config(config: TestnetOrderLifecycleConfig) -> list[str]:
    blockers: list[str] = []

    if config.require_no_live_flags and live_flags_detected():
        blockers.append("live_flags_detected")

    if config.quantity <= 0:
        blockers.append("quantity_must_be_positive")

    if config.price <= 0:
        blockers.append("price_must_be_positive")

    if config.quantity > config.max_qty:
        blockers.append("quantity_above_lifecycle_limit")

    if config.quantity * config.price > config.max_notional_usd:
        blockers.append("notional_above_lifecycle_limit")

    if not config.simulate and config.allow_real_submit and os.getenv("BINANCE_EXECUTION_MODE", "testnet").lower() != "testnet":
        blockers.append("execution_mode_must_be_testnet_for_real_testnet_order")

    return blockers


def export_lifecycle_json(
    payload: BaseModel | dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    name: str,
) -> Path:
    config = load_testnet_order_lifecycle_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path