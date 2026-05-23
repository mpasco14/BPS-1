from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ops.production_environment_guard import ProductionEnvironmentGuardReport
from ops.secrets_key_rotation_audit import SecretsKeyRotationAuditReport


load_dotenv()


LiveOrderAdapterStatus = Literal["DRY_RUN", "BLOCKED", "SUBMITTED"]


class LiveOrderAdapterConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/production")

    enabled: bool = False
    dry_run: bool = True
    allow_submission: bool = False
    required_confirmation: str = "I_ACCEPT_LIVE_RISK"

    max_margin_usd: float = 20.0
    max_notional_usd: float = 600.0
    max_leverage: int = 30
    allowed_symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT"])


class LiveOrderRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    side: Literal["BUY", "SELL"]
    order_type: Literal["LIMIT", "MARKET"] = "LIMIT"

    quantity: float
    price: float | None = None
    time_in_force: str = "GTC"
    reduce_only: bool = False

    notional_usd: float
    margin_usd: float
    leverage: int

    client_order_id: str | None = None
    session_name: str = "live_micro_session"

    production_guard_passed: bool = False
    secrets_audit_passed: bool = False
    live_risk_audit_passed: bool = False
    capital_ramp_validated: bool = False
    human_approval_valid: bool = False
    emergency_clear: bool = True

    confirmation_phrase: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class LiveOrderAdapterDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_order_adapter"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: LiveOrderAdapterStatus
    approved: bool
    submitted: bool = False
    dry_run: bool = True

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    payload: dict[str, Any] | None = None
    exchange_response: dict[str, Any] | None = None

    request: dict[str, Any]
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


def load_live_order_adapter_config() -> LiveOrderAdapterConfig:
    symbols = [
        item.strip().upper()
        for item in os.getenv("LIVE_ORDER_ADAPTER_ALLOWED_SYMBOLS", "BTCUSDT").split(",")
        if item.strip()
    ]

    return LiveOrderAdapterConfig(
        output_dir=Path(os.getenv("LIVE_ORDER_ADAPTER_OUTPUT_DIR", "artifacts/production")),
        enabled=env_bool("LIVE_ORDER_ADAPTER_ENABLED", False),
        dry_run=env_bool("LIVE_ORDER_ADAPTER_DRY_RUN", True),
        allow_submission=env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
        required_confirmation=os.getenv("LIVE_ORDER_ADAPTER_REQUIRED_CONFIRMATION", "I_ACCEPT_LIVE_RISK"),
        max_margin_usd=env_float("LIVE_ORDER_ADAPTER_MAX_MARGIN_USD", 20),
        max_notional_usd=env_float("LIVE_ORDER_ADAPTER_MAX_NOTIONAL_USD", 600),
        max_leverage=env_int("LIVE_ORDER_ADAPTER_MAX_LEVERAGE", 30),
        allowed_symbols=symbols,
    )


def build_binance_live_order_payload(request: LiveOrderRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "symbol": request.symbol,
        "side": request.side,
        "type": request.order_type,
        "quantity": request.quantity,
        "reduceOnly": request.reduce_only,
    }

    if request.order_type == "LIMIT":
        payload["price"] = request.price
        payload["timeInForce"] = request.time_in_force

    if request.client_order_id:
        payload["newClientOrderId"] = request.client_order_id

    return payload


def evaluate_live_order_adapter_gate(
    *,
    request: LiveOrderRequest | dict[str, Any],
    config: LiveOrderAdapterConfig | None = None,
    production_guard: ProductionEnvironmentGuardReport | dict[str, Any] | None = None,
    secrets_audit: SecretsKeyRotationAuditReport | dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    resolved_config = config or load_live_order_adapter_config()
    resolved_request = request if isinstance(request, LiveOrderRequest) else LiveOrderRequest.model_validate(request)

    blockers: list[str] = []
    warnings: list[str] = []

    if not resolved_config.enabled:
        blockers.append("live_order_adapter_disabled")

    if resolved_request.symbol.upper() not in resolved_config.allowed_symbols:
        blockers.append("symbol_not_allowed_for_live_adapter")

    if resolved_request.margin_usd > resolved_config.max_margin_usd:
        blockers.append("margin_above_live_adapter_limit")

    if resolved_request.notional_usd > resolved_config.max_notional_usd:
        blockers.append("notional_above_live_adapter_limit")

    if resolved_request.leverage > resolved_config.max_leverage:
        blockers.append("leverage_above_live_adapter_limit")

    if resolved_request.order_type == "LIMIT" and resolved_request.price is None:
        blockers.append("limit_order_price_missing")

    gate_flags = {
        "production_guard_passed": resolved_request.production_guard_passed,
        "secrets_audit_passed": resolved_request.secrets_audit_passed,
        "live_risk_audit_passed": resolved_request.live_risk_audit_passed,
        "capital_ramp_validated": resolved_request.capital_ramp_validated,
        "human_approval_valid": resolved_request.human_approval_valid,
        "emergency_clear": resolved_request.emergency_clear,
    }

    for name, value in gate_flags.items():
        if value is not True:
            blockers.append(name.replace("_passed", "_not_passed").replace("_valid", "_not_valid"))

    if resolved_request.confirmation_phrase != resolved_config.required_confirmation:
        blockers.append("required_live_confirmation_phrase_missing_or_invalid")

    if production_guard is not None:
        pg = (
            production_guard
            if isinstance(production_guard, ProductionEnvironmentGuardReport)
            else ProductionEnvironmentGuardReport.model_validate(production_guard)
        )
        if not pg.passed:
            blockers.append("production_guard_report_not_passed")

    if secrets_audit is not None:
        sa = (
            secrets_audit
            if isinstance(secrets_audit, SecretsKeyRotationAuditReport)
            else SecretsKeyRotationAuditReport.model_validate(secrets_audit)
        )
        if not sa.passed:
            blockers.append("secrets_audit_report_not_passed")

    if resolved_config.dry_run:
        warnings.append("live_order_adapter_dry_run_enabled")

    if not resolved_config.allow_submission:
        blockers.append("live_order_submission_not_allowed")

    return blockers, warnings


def submit_live_order(
    *,
    request: LiveOrderRequest | dict[str, Any],
    client_submit_order: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    config: LiveOrderAdapterConfig | None = None,
    production_guard: ProductionEnvironmentGuardReport | dict[str, Any] | None = None,
    secrets_audit: SecretsKeyRotationAuditReport | dict[str, Any] | None = None,
) -> LiveOrderAdapterDecision:
    resolved_config = config or load_live_order_adapter_config()
    resolved_request = request if isinstance(request, LiveOrderRequest) else LiveOrderRequest.model_validate(request)

    payload = build_binance_live_order_payload(resolved_request)

    blockers, warnings = evaluate_live_order_adapter_gate(
        request=resolved_request,
        config=resolved_config,
        production_guard=production_guard,
        secrets_audit=secrets_audit,
    )

    if blockers:
        return LiveOrderAdapterDecision(
            status="BLOCKED",
            approved=False,
            submitted=False,
            dry_run=resolved_config.dry_run,
            blockers=blockers,
            warnings=warnings,
            payload=payload,
            request=resolved_request.model_dump(mode="json"),
            config=resolved_config.model_dump(mode="json"),
        )

    if resolved_config.dry_run:
        return LiveOrderAdapterDecision(
            status="DRY_RUN",
            approved=True,
            submitted=False,
            dry_run=True,
            warnings=warnings,
            payload=payload,
            request=resolved_request.model_dump(mode="json"),
            config=resolved_config.model_dump(mode="json"),
        )

    if client_submit_order is None:
        return LiveOrderAdapterDecision(
            status="BLOCKED",
            approved=False,
            submitted=False,
            dry_run=False,
            blockers=["client_submit_order_missing"],
            warnings=warnings,
            payload=payload,
            request=resolved_request.model_dump(mode="json"),
            config=resolved_config.model_dump(mode="json"),
        )

    response = client_submit_order(payload)

    return LiveOrderAdapterDecision(
        status="SUBMITTED",
        approved=True,
        submitted=True,
        dry_run=False,
        warnings=warnings,
        payload=payload,
        exchange_response=response,
        request=resolved_request.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_live_order_adapter_decision(
    decision: LiveOrderAdapterDecision,
    *,
    output_dir: str | Path | None = None,
    name: str = "live_order_adapter_decision_latest",
) -> Path:
    config = load_live_order_adapter_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path