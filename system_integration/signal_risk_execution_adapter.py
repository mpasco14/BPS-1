from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from system_integration.execution_contract import (
    OrderPlan,
    RiskApprovalDecision,
    validate_execution_contract,
)


load_dotenv()


SignalDirection = Literal["BUY", "SELL", "HOLD"]


class SignalRiskExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/system_integration")
    min_confidence: float = 0.60
    min_edge: float = 0.01
    default_dry_run: bool = True


class SignalDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    signal_id: str = Field(default_factory=lambda: f"signal_{uuid4().hex}")

    symbol: str = "BTCUSDT"
    timeframe: str = "5m"
    direction: SignalDirection = "HOLD"

    probability: float = 0.5
    confidence: float = 0.0
    edge: float = 0.0

    suggested_quantity: float = 0.0
    suggested_price: float | None = None
    suggested_notional_usd: float = 0.0
    suggested_margin_usd: float = 0.0
    suggested_leverage: int = 1

    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalRiskExecutionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "signal_risk_execution_pipeline_adapter"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    approved: bool
    status: str

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    signal: dict[str, Any]
    risk_decision: dict[str, Any]
    order_plan: dict[str, Any] | None = None
    execution_contract: dict[str, Any] | None = None


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


def load_signal_risk_execution_config() -> SignalRiskExecutionConfig:
    return SignalRiskExecutionConfig(
        output_dir=Path(os.getenv("PIPELINE_ADAPTER_OUTPUT_DIR", "artifacts/system_integration")),
        min_confidence=env_float("PIPELINE_MIN_CONFIDENCE", 0.60),
        min_edge=env_float("PIPELINE_MIN_EDGE", 0.01),
        default_dry_run=env_bool("PIPELINE_DEFAULT_DRY_RUN", True),
    )


def build_order_plan_from_signal(
    *,
    signal: SignalDecision,
    dry_run: bool = True,
) -> OrderPlan | None:
    if signal.direction == "HOLD":
        return None

    return OrderPlan(
        order_plan_id=f"order_plan_{signal.signal_id}",
        symbol=signal.symbol,
        side=signal.direction,
        order_type="LIMIT",
        quantity=signal.suggested_quantity,
        price=signal.suggested_price,
        notional_usd=signal.suggested_notional_usd,
        margin_usd=signal.suggested_margin_usd,
        leverage=signal.suggested_leverage,
        dry_run=dry_run,
        idempotency_key=f"idempotency_{signal.signal_id}",
        source_signal_id=signal.signal_id,
        metadata={
            "timeframe": signal.timeframe,
            "confidence": signal.confidence,
            "edge": signal.edge,
        },
    )


def adapt_signal_to_risk_execution(
    *,
    signal: SignalDecision | dict[str, Any],
    risk_decision: RiskApprovalDecision | dict[str, Any],
    execution_mode: str = "paper",
    live_submission_allowed: bool = False,
    human_approval_valid: bool = False,
    production_guard_passed: bool = False,
    safe_mode_active: bool = False,
    kill_switch_active: bool = False,
    config: SignalRiskExecutionConfig | None = None,
) -> SignalRiskExecutionResult:
    resolved_config = config or load_signal_risk_execution_config()
    parsed_signal = signal if isinstance(signal, SignalDecision) else SignalDecision.model_validate(signal)
    parsed_risk = risk_decision if isinstance(risk_decision, RiskApprovalDecision) else RiskApprovalDecision.model_validate(risk_decision)

    blockers: list[str] = []
    warnings: list[str] = []

    if parsed_signal.direction == "HOLD":
        blockers.append("signal_direction_hold")

    if parsed_signal.confidence < resolved_config.min_confidence:
        blockers.append("signal_confidence_below_minimum")

    if parsed_signal.edge < resolved_config.min_edge:
        blockers.append("signal_edge_below_minimum")

    if not parsed_risk.approved:
        blockers.append("risk_not_approved")

    order_plan = None
    contract = None

    if not blockers:
        order_plan = build_order_plan_from_signal(
            signal=parsed_signal,
            dry_run=resolved_config.default_dry_run,
        )

        contract = validate_execution_contract(
            order_plan=order_plan,
            risk_decision=parsed_risk,
            execution_mode=execution_mode,
            live_submission_allowed=live_submission_allowed,
            human_approval_valid=human_approval_valid,
            production_guard_passed=production_guard_passed,
            safe_mode_active=safe_mode_active,
            kill_switch_active=kill_switch_active,
        )

        if not contract.approved:
            blockers.extend([f"contract:{item}" for item in contract.blockers])

        warnings.extend([f"contract:{item}" for item in contract.warnings])

    approved = not blockers

    return SignalRiskExecutionResult(
        approved=approved,
        status="APPROVED" if approved and not warnings else "WARN" if approved else "BLOCKED",
        blockers=blockers,
        warnings=warnings,
        signal=parsed_signal.model_dump(mode="json"),
        risk_decision=parsed_risk.model_dump(mode="json"),
        order_plan=order_plan.model_dump(mode="json") if order_plan else None,
        execution_contract=contract.model_dump(mode="json") if contract else None,
    )


def export_signal_risk_execution_result(
    result: SignalRiskExecutionResult,
    *,
    output_dir: str | Path | None = None,
    name: str = "signal_risk_execution_latest",
) -> Path:
    config = load_signal_risk_execution_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path