"""
Binance Futures cancel order rules.

Responsabilidades:
- Avaliar quando uma ordem aberta deve ser cancelada.
- Cancelar ordem via BinanceFuturesRestClient quando aplicável.
- Bloquear ordem se edge sumiu, spread piorou, kill switch ativou ou idade excedeu.

Este módulo NÃO decide entrada.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from execution.binance_futures_client import BinanceFuturesRestClient
from risk.kill_switch import KillSwitchState


load_dotenv()


CancelReason = Literal[
    "edge_lost",
    "spread_above_limit",
    "near_expiry",
    "kill_switch_active",
    "order_too_old",
]


class OpenOrderState(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    client_order_id: str | None = None
    order_id: int | None = None

    side: str
    price: float
    quantity: float

    status: str = "NEW"
    timeframe: str = "5m"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    edge_valid: bool = True
    spread_pct: float = 0.0
    time_to_expiry_seconds: float | None = None

    filled_ratio: float = 0.0

    metadata: dict[str, Any] = Field(default_factory=dict)


class CancelPolicy(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_order_age_seconds: float = 60
    max_spread_pct: float = 0.002
    min_time_to_expiry_seconds: float = 120

    cancel_on_edge_lost: bool = True
    cancel_on_kill_switch: bool = True


class CancelDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    should_cancel: bool
    reasons: list[CancelReason] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)

    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    order: dict[str, Any] = Field(default_factory=dict)


class CancelExecutionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    attempted: bool
    cancelled: bool

    decision: dict[str, Any]
    response: dict[str, Any] | None = None

    error: str | None = None


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_cancel_policy() -> CancelPolicy:
    return CancelPolicy(
        max_order_age_seconds=env_float("CANCEL_ORDER_MAX_ORDER_AGE_SECONDS", 60),
        max_spread_pct=env_float("CANCEL_ORDER_MAX_SPREAD_PCT", 0.002),
        min_time_to_expiry_seconds=env_float("CANCEL_ORDER_MIN_TIME_TO_EXPIRY_SECONDS", 120),
        cancel_on_edge_lost=env_bool("CANCEL_ORDER_CANCEL_ON_EDGE_LOST", True),
        cancel_on_kill_switch=env_bool("CANCEL_ORDER_CANCEL_ON_KILL_SWITCH", True),
    )


def order_age_seconds(order: OpenOrderState, *, now: datetime | None = None) -> float:
    reference = now or datetime.now(timezone.utc)
    created = order.created_at

    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    return max(0.0, (reference - created).total_seconds())


def evaluate_cancel_order(
    order: OpenOrderState | dict[str, Any],
    *,
    policy: CancelPolicy | None = None,
    now: datetime | None = None,
    edge_valid: bool | None = None,
    spread_pct: float | None = None,
    time_to_expiry_seconds: float | None = None,
    kill_switch_state: KillSwitchState | None = None,
) -> CancelDecision:
    parsed = order if isinstance(order, OpenOrderState) else OpenOrderState.model_validate(order)
    resolved_policy = policy or load_cancel_policy()

    current_edge_valid = edge_valid if edge_valid is not None else parsed.edge_valid
    current_spread = spread_pct if spread_pct is not None else parsed.spread_pct
    current_time_to_expiry = (
        time_to_expiry_seconds
        if time_to_expiry_seconds is not None
        else parsed.time_to_expiry_seconds
    )

    reasons: list[CancelReason] = []
    details: list[str] = []

    if resolved_policy.cancel_on_edge_lost and not current_edge_valid:
        reasons.append("edge_lost")
        details.append("edge_valid=false")

    if current_spread > resolved_policy.max_spread_pct:
        reasons.append("spread_above_limit")
        details.append(f"spread_pct:{current_spread:.6f}")

    if (
        current_time_to_expiry is not None
        and current_time_to_expiry < resolved_policy.min_time_to_expiry_seconds
    ):
        reasons.append("near_expiry")
        details.append(f"time_to_expiry_seconds:{current_time_to_expiry:.2f}")

    if (
        resolved_policy.cancel_on_kill_switch
        and kill_switch_state is not None
        and kill_switch_state.active
    ):
        reasons.append("kill_switch_active")
        details.extend([f"kill_switch:{trigger}" for trigger in kill_switch_state.triggers])

    age = order_age_seconds(parsed, now=now)

    if age > resolved_policy.max_order_age_seconds:
        reasons.append("order_too_old")
        details.append(f"order_age_seconds:{age:.2f}")

    return CancelDecision(
        should_cancel=bool(reasons),
        reasons=reasons,
        details=details,
        order=parsed.model_dump(mode="json"),
    )


def cancel_order_if_needed(
    *,
    order: OpenOrderState | dict[str, Any],
    decision: CancelDecision | None = None,
    client: BinanceFuturesRestClient | None = None,
) -> CancelExecutionResult:
    parsed = order if isinstance(order, OpenOrderState) else OpenOrderState.model_validate(order)
    resolved_decision = decision or evaluate_cancel_order(parsed)

    if not resolved_decision.should_cancel:
        return CancelExecutionResult(
            attempted=False,
            cancelled=False,
            decision=resolved_decision.model_dump(mode="json"),
            response=None,
        )

    try:
        resolved_client = client or BinanceFuturesRestClient()

        response = resolved_client.cancel_order(
            symbol=parsed.symbol,
            order_id=parsed.order_id,
            orig_client_order_id=parsed.client_order_id,
        )

        return CancelExecutionResult(
            attempted=True,
            cancelled=True,
            decision=resolved_decision.model_dump(mode="json"),
            response=response,
        )
    except Exception as exc:
        return CancelExecutionResult(
            attempted=True,
            cancelled=False,
            decision=resolved_decision.model_dump(mode="json"),
            response=None,
            error=str(exc),
        )


def cancel_decision_to_dict(decision: CancelDecision) -> dict[str, Any]:
    return decision.model_dump(mode="json")