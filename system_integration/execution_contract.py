from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "STOP"]
ExecutionContractStatus = Literal["APPROVED", "DRY_RUN_READY", "BLOCKED", "WARN"]


class ExecutionContractConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/system_integration")

    require_idempotency: bool = True
    require_risk_approval: bool = True
    require_human_approval_for_live: bool = True
    require_production_guard_for_live: bool = True
    block_live_when_dry_run: bool = False


class OrderPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    order_plan_id: str
    symbol: str = "BTCUSDT"
    side: OrderSide
    order_type: OrderType = "LIMIT"

    quantity: float
    price: float | None = None
    notional_usd: float
    margin_usd: float
    leverage: int = 1

    reduce_only: bool = False
    dry_run: bool = True

    idempotency_key: str | None = None
    source_signal_id: str | None = None
    decision_id: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    approved: bool
    risk_score: float | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionContractReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "execution_contract_validator"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ExecutionContractStatus
    approved: bool
    dry_run: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    order_plan: dict[str, Any] | None = None
    risk_decision: dict[str, Any] | None = None
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_execution_contract_config() -> ExecutionContractConfig:
    return ExecutionContractConfig(
        output_dir=Path(os.getenv("EXECUTION_CONTRACT_OUTPUT_DIR", "artifacts/system_integration")),
        require_idempotency=env_bool("EXECUTION_CONTRACT_REQUIRE_IDEMPOTENCY", True),
        require_risk_approval=env_bool("EXECUTION_CONTRACT_REQUIRE_RISK_APPROVAL", True),
        require_human_approval_for_live=env_bool("EXECUTION_CONTRACT_REQUIRE_HUMAN_APPROVAL_FOR_LIVE", True),
        require_production_guard_for_live=env_bool("EXECUTION_CONTRACT_REQUIRE_PRODUCTION_GUARD_FOR_LIVE", True),
        block_live_when_dry_run=env_bool("EXECUTION_CONTRACT_BLOCK_LIVE_WHEN_DRY_RUN", False),
    )


def validate_execution_contract(
    *,
    order_plan: OrderPlan | dict[str, Any] | None,
    risk_decision: RiskApprovalDecision | dict[str, Any] | None = None,
    execution_mode: str = "paper",
    live_submission_allowed: bool = False,
    human_approval_valid: bool = False,
    production_guard_passed: bool = False,
    safe_mode_active: bool = False,
    kill_switch_active: bool = False,
    config: ExecutionContractConfig | None = None,
) -> ExecutionContractReport:
    resolved_config = config or load_execution_contract_config()

    blockers: list[str] = []
    warnings: list[str] = []

    parsed_order = None
    parsed_risk = None

    if order_plan is None:
        blockers.append("order_plan_missing")
    else:
        parsed_order = order_plan if isinstance(order_plan, OrderPlan) else OrderPlan.model_validate(order_plan)

    if risk_decision is not None:
        parsed_risk = risk_decision if isinstance(risk_decision, RiskApprovalDecision) else RiskApprovalDecision.model_validate(risk_decision)

    if parsed_order is not None:
        if parsed_order.quantity <= 0:
            blockers.append("quantity_must_be_positive")

        if parsed_order.notional_usd <= 0:
            blockers.append("notional_must_be_positive")

        if parsed_order.margin_usd < 0:
            blockers.append("margin_cannot_be_negative")

        if parsed_order.leverage <= 0:
            blockers.append("leverage_must_be_positive")

        if parsed_order.order_type in {"LIMIT", "STOP"} and parsed_order.price is None:
            blockers.append("price_required_for_limit_or_stop")

        if resolved_config.require_idempotency and not parsed_order.idempotency_key:
            blockers.append("idempotency_key_required")

        if safe_mode_active and not parsed_order.reduce_only:
            blockers.append("safe_mode_allows_reduce_only_only")

        if kill_switch_active:
            blockers.append("kill_switch_active_blocks_execution")

        if parsed_order.dry_run:
            warnings.append("order_plan_is_dry_run")

    if resolved_config.require_risk_approval:
        if parsed_risk is None:
            blockers.append("risk_decision_missing")
        elif not parsed_risk.approved:
            blockers.append("risk_decision_not_approved")
            blockers.extend([f"risk:{item}" for item in parsed_risk.blockers])

    live_intent = execution_mode == "live" or live_submission_allowed

    if live_intent:
        if parsed_order is not None and parsed_order.dry_run and resolved_config.block_live_when_dry_run:
            blockers.append("dry_run_order_cannot_be_live_submitted")

        if resolved_config.require_human_approval_for_live and not human_approval_valid:
            blockers.append("human_approval_required_for_live_execution")

        if resolved_config.require_production_guard_for_live and not production_guard_passed:
            blockers.append("production_guard_required_for_live_execution")

        if not live_submission_allowed:
            blockers.append("live_submission_not_allowed")

    approved = not blockers

    if approved and parsed_order is not None and parsed_order.dry_run:
        status: ExecutionContractStatus = "DRY_RUN_READY"
    elif approved and warnings:
        status = "WARN"
    elif approved:
        status = "APPROVED"
    else:
        status = "BLOCKED"

    return ExecutionContractReport(
        status=status,
        approved=approved,
        dry_run=parsed_order.dry_run if parsed_order is not None else True,
        blockers=blockers,
        warnings=warnings,
        order_plan=parsed_order.model_dump(mode="json") if parsed_order else None,
        risk_decision=parsed_risk.model_dump(mode="json") if parsed_risk else None,
        config=resolved_config.model_dump(mode="json"),
    )


def export_execution_contract_report(
    report: ExecutionContractReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "execution_contract_latest",
) -> Path:
    config = load_execution_contract_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path