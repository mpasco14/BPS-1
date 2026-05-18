"""
Binance Futures order router.

Responsabilidades:
- Receber sinal aprovado ou candidato.
- Rodar risk assessment e approval final.
- Checar kill switch.
- Construir ordem LIMIT.
- Enviar via client em modo paper/testnet/live-controlado.
- Registrar ordem roteada em memória.

Este módulo NÃO ignora risk_manager.
Este módulo NÃO permite live trading se o client bloquear.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from execution.binance_futures_client import BinanceFuturesRestClient
from execution.limit_order import (
    LimitOrderPayload,
    SymbolTradingRules,
    build_limit_order_from_plan,
    limit_order_to_params,
)
from risk.exposure import ExposureSnapshot, default_exposure_snapshot
from risk.kill_switch import KillSwitchInput, KillSwitchState, evaluate_kill_switch
from risk.risk_manager import (
    RiskAssessment,
    RiskProfile,
    SignalApprovalResult,
    approve_signal,
    assess_signal_risk,
)
from strategy.signal_engine import TradingSignal


load_dotenv()


RouteDecision = Literal["ROUTED", "BLOCKED"]


class RoutedOrderRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "order_router"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str

    decision: RouteDecision
    status: str

    client_order_id: str | None = None
    exchange_order_id: str | None = None

    order_payload: dict[str, Any] | None = None
    exchange_response: dict[str, Any] | None = None

    signal: dict[str, Any] | None = None
    risk_assessment: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    kill_switch: dict[str, Any] | None = None

    blockers: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    routed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrderRouteResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    decision: RouteDecision
    record: dict[str, Any]

    should_publish: bool = False
    kafka_topic: str | None = None


class InMemoryOrderRegistry:
    def __init__(self) -> None:
        self._orders: dict[str, RoutedOrderRecord] = {}

    def register(self, record: RoutedOrderRecord) -> RoutedOrderRecord:
        key = record.client_order_id or f"{record.symbol}:{len(self._orders) + 1}"
        self._orders[key] = record
        return record

    def get(self, client_order_id: str) -> RoutedOrderRecord | None:
        return self._orders.get(client_order_id)

    def list_orders(self) -> list[RoutedOrderRecord]:
        return list(self._orders.values())

    def count(self) -> int:
        return len(self._orders)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def extract_order_ids(response: dict[str, Any], payload: LimitOrderPayload) -> tuple[str | None, str | None]:
    client_id = (
        response.get("clientOrderId")
        or response.get("origClientOrderId")
        or payload.newClientOrderId
    )

    order_id = response.get("orderId")

    if order_id is not None:
        order_id = str(order_id)

    return str(client_id) if client_id is not None else None, order_id


def route_signal_to_order(
    *,
    signal: TradingSignal | dict[str, Any],
    entry_price: float,
    rules: SymbolTradingRules,
    client: BinanceFuturesRestClient | None = None,
    profile: RiskProfile | None = None,
    exposure_snapshot: ExposureSnapshot | None = None,
    kill_switch_input: KillSwitchInput | dict[str, Any] | None = None,
    market_liquidity_usd: float | None = None,
    submit_order: bool | None = None,
    use_test_endpoint: bool | None = None,
    registry: InMemoryOrderRegistry | None = None,
) -> OrderRouteResult:
    parsed_signal = signal if isinstance(signal, TradingSignal) else TradingSignal.model_validate(signal)

    snapshot = exposure_snapshot or default_exposure_snapshot()

    kill_state: KillSwitchState = evaluate_kill_switch(kill_switch_input or {})

    if kill_state.active:
        record = RoutedOrderRecord(
            symbol=parsed_signal.symbol,
            timeframe=parsed_signal.timeframe,
            decision="BLOCKED",
            status="KILL_SWITCH_ACTIVE",
            signal=parsed_signal.model_dump(mode="json"),
            kill_switch=kill_state.model_dump(mode="json"),
            blockers=[f"kill_switch:{trigger}" for trigger in kill_state.triggers],
        )

        if registry:
            registry.register(record)

        return OrderRouteResult(
            decision="BLOCKED",
            record=record.model_dump(mode="json"),
            should_publish=False,
        )

    assessment: RiskAssessment = assess_signal_risk(
        signal=parsed_signal,
        entry_price=entry_price,
        account_state=None,
        profile=profile,
    )

    approval: SignalApprovalResult = approve_signal(
        parsed_signal,
        risk_assessment=assessment,
        exposure_snapshot=snapshot,
        market_liquidity_usd=market_liquidity_usd,
    )

    if not approval.approved:
        record = RoutedOrderRecord(
            symbol=parsed_signal.symbol,
            timeframe=parsed_signal.timeframe,
            decision="BLOCKED",
            status="RISK_BLOCKED",
            signal=parsed_signal.model_dump(mode="json"),
            risk_assessment=assessment.model_dump(mode="json"),
            approval=approval.model_dump(mode="json"),
            kill_switch=kill_state.model_dump(mode="json"),
            blockers=approval.blockers,
            reasons=approval.reasons,
        )

        if registry:
            registry.register(record)

        return OrderRouteResult(
            decision="BLOCKED",
            record=record.model_dump(mode="json"),
            should_publish=False,
        )

    if assessment.order_plan is None:
        record = RoutedOrderRecord(
            symbol=parsed_signal.symbol,
            timeframe=parsed_signal.timeframe,
            decision="BLOCKED",
            status="MISSING_ORDER_PLAN",
            signal=parsed_signal.model_dump(mode="json"),
            risk_assessment=assessment.model_dump(mode="json"),
            approval=approval.model_dump(mode="json"),
            blockers=["missing_order_plan"],
        )

        if registry:
            registry.register(record)

        return OrderRouteResult(
            decision="BLOCKED",
            record=record.model_dump(mode="json"),
            should_publish=False,
        )

    order_payload = build_limit_order_from_plan(
        plan=assessment.order_plan,
        rules=rules,
    )

    order_params = limit_order_to_params(order_payload)

    should_submit = (
        submit_order
        if submit_order is not None
        else env_bool("ORDER_ROUTER_SUBMIT_ORDERS", True)
    )

    should_use_test_endpoint = (
        use_test_endpoint
        if use_test_endpoint is not None
        else env_bool("ORDER_ROUTER_USE_TEST_ENDPOINT", False)
    )

    exchange_response: dict[str, Any] | None = None

    if should_submit:
        resolved_client = client or BinanceFuturesRestClient()

        if should_use_test_endpoint:
            exchange_response = resolved_client.new_order_test(order_params)
        else:
            exchange_response = resolved_client.new_order(order_params)
    else:
        exchange_response = {
            "paper": True,
            "not_submitted": True,
            "params": order_params,
        }

    client_order_id, exchange_order_id = extract_order_ids(
        exchange_response or {},
        order_payload,
    )

    status = str(
        (exchange_response or {}).get("status")
        or ("PAPER_ACCEPTED" if (exchange_response or {}).get("paper") else "SUBMITTED")
    )

    record = RoutedOrderRecord(
        symbol=parsed_signal.symbol,
        timeframe=parsed_signal.timeframe,
        decision="ROUTED",
        status=status,
        client_order_id=client_order_id,
        exchange_order_id=exchange_order_id,
        order_payload=order_params,
        exchange_response=exchange_response,
        signal=parsed_signal.model_dump(mode="json"),
        risk_assessment=assessment.model_dump(mode="json"),
        approval=approval.model_dump(mode="json"),
        kill_switch=kill_state.model_dump(mode="json"),
        blockers=[],
        reasons=approval.reasons,
    )

    if registry:
        registry.register(record)

    return OrderRouteResult(
        decision="ROUTED",
        record=record.model_dump(mode="json"),
        should_publish=env_bool("ORDER_ROUTER_PUBLISH_TO_KAFKA", False),
        kafka_topic=os.getenv("ORDER_ROUTER_ORDERS_TOPIC", "orders"),
    )