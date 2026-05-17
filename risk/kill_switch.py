"""
Kill switch / circuit breaker.

Responsabilidades:
- Bloquear novas entradas em condições críticas.
- Sinalizar cancelamento de ordens abertas.
- Servir como camada de segurança antes do executor.

Este módulo NÃO cancela ordens diretamente.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


class KillSwitchInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    ws_disconnected_seconds: float = 0.0
    btc_price_divergence_pct: float = 0.0
    spread_pct: float = 0.0
    slippage_pct: float = 0.0
    daily_drawdown_pct: float = 0.0
    model_ood: bool = False
    api_error_count: int = 0


class KillSwitchState(BaseModel):
    model_config = ConfigDict(extra="allow")

    active: bool
    cancel_open_orders: bool

    triggers: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    raw: dict[str, Any] = Field(default_factory=dict)


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


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def evaluate_kill_switch(payload: KillSwitchInput | dict[str, Any]) -> KillSwitchState:
    data = payload if isinstance(payload, KillSwitchInput) else KillSwitchInput.model_validate(payload)

    triggers: list[str] = []

    if not env_bool("KILL_SWITCH_ENABLED", True):
        return KillSwitchState(
            active=False,
            cancel_open_orders=False,
            triggers=[],
            raw=data.model_dump(mode="json"),
        )

    if data.ws_disconnected_seconds > env_float("KILL_SWITCH_MAX_WS_DISCONNECTED_SECONDS", 30.0):
        triggers.append("websocket_disconnected_too_long")

    if data.btc_price_divergence_pct > env_float("KILL_SWITCH_MAX_BTC_PRICE_DIVERGENCE_PCT", 0.005):
        triggers.append("btc_price_divergence_above_limit")

    if data.spread_pct > env_float("KILL_SWITCH_MAX_SPREAD_PCT", 0.002):
        triggers.append("spread_above_limit")

    if data.slippage_pct > env_float("KILL_SWITCH_MAX_SLIPPAGE_PCT", 0.001):
        triggers.append("slippage_above_limit")

    max_daily_loss_pct = env_float("RISK_MAX_DAILY_LOSS_PCT", 0.03)

    if data.daily_drawdown_pct >= max_daily_loss_pct:
        triggers.append("daily_drawdown_limit_reached")

    if env_bool("KILL_SWITCH_TRIGGER_ON_MODEL_OOD", True) and data.model_ood:
        triggers.append("model_out_of_distribution")

    if data.api_error_count >= env_int("KILL_SWITCH_MAX_API_ERRORS", 5):
        triggers.append("api_repeated_errors")

    active = bool(triggers)

    return KillSwitchState(
        active=active,
        cancel_open_orders=active and env_bool("KILL_SWITCH_CANCEL_OPEN_ORDERS", True),
        triggers=triggers,
        raw=data.model_dump(mode="json"),
    )


def should_cancel_open_orders(state: KillSwitchState) -> bool:
    return state.active and state.cancel_open_orders


def kill_switch_to_dict(state: KillSwitchState) -> dict[str, Any]:
    return state.model_dump(mode="json")