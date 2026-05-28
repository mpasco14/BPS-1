from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from testnet_supervision.credential_readiness import TestnetCredentialReadinessReport


load_dotenv()

__test__ = False


SessionPlanStatus = Literal["PASS", "WARN", "FAIL"]


class SupervisedTestnetSessionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_supervision")

    session_name: str = "v1_rc1_testnet_supervised"
    duration_minutes: int = 30

    symbol: str = "BTCUSDT"
    timeframe: str = "5m"

    dry_run: bool = True
    allow_testnet_order_submission: bool = False

    max_orders: int = 3
    max_notional_usd: float = 25.0
    max_margin_usd: float = 5.0
    max_leverage: int = 12
    max_open_positions: int = 1
    max_rejections: int = 0

    require_flat_at_end: bool = True
    require_operator_present: bool = True
    require_kill_switch_ready: bool = True


class SupervisedTestnetSessionPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "supervised_testnet_session_plan"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str
    planned_start_at: datetime
    planned_end_at: datetime
    duration_minutes: int

    symbol: str
    timeframe: str

    dry_run: bool = True
    allow_testnet_order_submission: bool = False

    max_orders: int
    max_notional_usd: float
    max_margin_usd: float
    max_leverage: int
    max_open_positions: int
    max_rejections: int

    require_flat_at_end: bool = True
    require_operator_present: bool = True
    require_kill_switch_ready: bool = True

    operator: str = "operator"

    planned_checks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupervisedTestnetSessionPlanReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "supervised_testnet_session_plan_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: SessionPlanStatus
    passed: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    plan: dict[str, Any]
    credential_readiness: dict[str, Any] | None = None
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_supervised_testnet_session_config() -> SupervisedTestnetSessionConfig:
    return SupervisedTestnetSessionConfig(
        output_dir=Path(os.getenv("SUPERVISED_TESTNET_SESSION_OUTPUT_DIR", "artifacts/testnet_supervision")),
        session_name=os.getenv("SUPERVISED_TESTNET_SESSION_NAME", "v1_rc1_testnet_supervised"),
        duration_minutes=env_int("SUPERVISED_TESTNET_DURATION_MINUTES", 30),
        symbol=os.getenv("SUPERVISED_TESTNET_SYMBOL", "BTCUSDT"),
        timeframe=os.getenv("SUPERVISED_TESTNET_TIMEFRAME", "5m"),
        dry_run=env_bool("SUPERVISED_TESTNET_DRY_RUN", True),
        allow_testnet_order_submission=env_bool("SUPERVISED_TESTNET_ALLOW_TESTNET_ORDER_SUBMISSION", False),
        max_orders=env_int("SUPERVISED_TESTNET_MAX_ORDERS", 3),
        max_notional_usd=env_float("SUPERVISED_TESTNET_MAX_NOTIONAL_USD", 25),
        max_margin_usd=env_float("SUPERVISED_TESTNET_MAX_MARGIN_USD", 5),
        max_leverage=env_int("SUPERVISED_TESTNET_MAX_LEVERAGE", 12),
        max_open_positions=env_int("SUPERVISED_TESTNET_MAX_OPEN_POSITIONS", 1),
        max_rejections=env_int("SUPERVISED_TESTNET_MAX_REJECTIONS", 0),
        require_flat_at_end=env_bool("SUPERVISED_TESTNET_REQUIRE_FLAT_AT_END", True),
        require_operator_present=env_bool("SUPERVISED_TESTNET_REQUIRE_OPERATOR_PRESENT", True),
        require_kill_switch_ready=env_bool("SUPERVISED_TESTNET_REQUIRE_KILL_SWITCH_READY", True),
    )


def build_supervised_testnet_session_plan(
    *,
    session_name: str | None = None,
    duration_minutes: int | None = None,
    operator: str = "operator",
    metadata: dict[str, Any] | None = None,
) -> SupervisedTestnetSessionPlan:
    config = load_supervised_testnet_session_config()

    resolved_duration = duration_minutes or config.duration_minutes
    start = datetime.now(timezone.utc).replace(microsecond=0)
    end = start + timedelta(minutes=resolved_duration)

    return SupervisedTestnetSessionPlan(
        session_name=session_name or config.session_name,
        planned_start_at=start,
        planned_end_at=end,
        duration_minutes=resolved_duration,
        symbol=config.symbol,
        timeframe=config.timeframe,
        dry_run=config.dry_run,
        allow_testnet_order_submission=config.allow_testnet_order_submission,
        max_orders=config.max_orders,
        max_notional_usd=config.max_notional_usd,
        max_margin_usd=config.max_margin_usd,
        max_leverage=config.max_leverage,
        max_open_positions=config.max_open_positions,
        max_rejections=config.max_rejections,
        require_flat_at_end=config.require_flat_at_end,
        require_operator_present=config.require_operator_present,
        require_kill_switch_ready=config.require_kill_switch_ready,
        operator=operator,
        planned_checks=[
            "credential_endpoint_readiness",
            "runtime_context_testnet_safe_flags",
            "preflight_quality_gate",
            "operator_presence_confirmed",
            "kill_switch_available",
            "safe_mode_available",
            "max_orders_enforced",
            "evidence_collection_enabled",
            "portfolio_reconciliation_required",
            "session_review_gate_required",
        ],
        metadata=metadata or {},
    )


def evaluate_supervised_testnet_session_plan(
    *,
    plan: SupervisedTestnetSessionPlan | dict[str, Any],
    credential_readiness: TestnetCredentialReadinessReport | dict[str, Any] | None = None,
    config: SupervisedTestnetSessionConfig | None = None,
) -> SupervisedTestnetSessionPlanReport:
    resolved_config = config or load_supervised_testnet_session_config()
    parsed_plan = plan if isinstance(plan, SupervisedTestnetSessionPlan) else SupervisedTestnetSessionPlan.model_validate(plan)

    parsed_credential = None
    if credential_readiness is not None:
        parsed_credential = (
            credential_readiness
            if isinstance(credential_readiness, TestnetCredentialReadinessReport)
            else TestnetCredentialReadinessReport.model_validate(credential_readiness)
        )

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if parsed_plan.duration_minutes <= 0:
        blockers.append("duration_minutes_must_be_positive")

    if parsed_plan.max_orders <= 0:
        blockers.append("max_orders_must_be_positive")

    if parsed_plan.max_notional_usd > resolved_config.max_notional_usd:
        blockers.append("max_notional_above_config_limit")

    if parsed_plan.max_margin_usd > resolved_config.max_margin_usd:
        blockers.append("max_margin_above_config_limit")

    if parsed_plan.max_leverage > resolved_config.max_leverage:
        blockers.append("max_leverage_above_config_limit")

    if parsed_plan.max_open_positions > resolved_config.max_open_positions:
        blockers.append("max_open_positions_above_config_limit")

    if not parsed_plan.dry_run and not parsed_plan.allow_testnet_order_submission:
        blockers.append("testnet_order_submission_not_allowed")

    if parsed_plan.allow_testnet_order_submission and parsed_plan.dry_run:
        warnings.append("testnet_order_submission_enabled_but_plan_is_dry_run")

    if parsed_plan.allow_testnet_order_submission:
        warnings.append("real_testnet_order_submission_requires_operator_supervision")

    if parsed_plan.require_operator_present and not parsed_plan.operator:
        blockers.append("operator_required")

    if parsed_plan.require_kill_switch_ready is False:
        blockers.append("kill_switch_required_for_supervised_testnet")

    if parsed_credential is not None and not parsed_credential.passed:
        blockers.append("credential_readiness_not_passed")
        blockers.extend([f"credential:{item}" for item in parsed_credential.blockers])

    if not parsed_plan.planned_checks:
        blockers.append("planned_checks_missing")

    recommendations.append("Começar com sessão curta de 30 minutos antes de sessões longas.")
    recommendations.append("Encerrar sessão testnet em posição flat e com reconciliação PASS.")

    passed = not blockers

    return SupervisedTestnetSessionPlanReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        plan=parsed_plan.model_dump(mode="json"),
        credential_readiness=parsed_credential.model_dump(mode="json") if parsed_credential else None,
        config=resolved_config.model_dump(mode="json"),
    )


def export_supervised_testnet_session_plan_report(
    report: SupervisedTestnetSessionPlanReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "supervised_testnet_session_plan_report",
) -> Path:
    config = load_supervised_testnet_session_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path