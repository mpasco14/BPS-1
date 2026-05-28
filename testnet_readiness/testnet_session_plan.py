from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


PlanStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetSessionPlanConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_readiness")

    session_name: str = "testnet_v1_validation"
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"
    dry_run: bool = True

    max_notional_usd: float = 100.0
    max_margin_usd: float = 10.0
    max_leverage: int = 12

    require_e2e: bool = True
    require_scenario_testing: bool = True
    require_kill_switch: bool = True
    require_reconciliation: bool = True


class TestnetSessionPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_session_plan"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str
    symbol: str
    timeframe: str
    dry_run: bool = True

    max_notional_usd: float
    max_margin_usd: float
    max_leverage: int

    e2e_passed: bool = False
    scenario_testing_passed: bool = False
    kill_switch_test_passed: bool = False
    reconciliation_required: bool = True

    planned_steps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestnetSessionPlanReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_session_plan_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: PlanStatus
    passed: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    plan: dict[str, Any]
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


def load_testnet_session_plan_config() -> TestnetSessionPlanConfig:
    return TestnetSessionPlanConfig(
        output_dir=Path(os.getenv("TESTNET_SESSION_PLAN_OUTPUT_DIR", "artifacts/testnet_readiness")),
        session_name=os.getenv("TESTNET_SESSION_NAME", "testnet_v1_validation"),
        symbol=os.getenv("TESTNET_SESSION_SYMBOL", "BTCUSDT"),
        timeframe=os.getenv("TESTNET_SESSION_TIMEFRAME", "5m"),
        dry_run=env_bool("TESTNET_SESSION_DRY_RUN", True),
        max_notional_usd=env_float("TESTNET_SESSION_MAX_NOTIONAL_USD", 100),
        max_margin_usd=env_float("TESTNET_SESSION_MAX_MARGIN_USD", 10),
        max_leverage=env_int("TESTNET_SESSION_MAX_LEVERAGE", 12),
        require_e2e=env_bool("TESTNET_SESSION_REQUIRE_E2E", True),
        require_scenario_testing=env_bool("TESTNET_SESSION_REQUIRE_SCENARIO_TESTING", True),
        require_kill_switch=env_bool("TESTNET_SESSION_REQUIRE_KILL_SWITCH", True),
        require_reconciliation=env_bool("TESTNET_SESSION_REQUIRE_RECONCILIATION", True),
    )


def build_testnet_session_plan(
    *,
    session_name: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    dry_run: bool | None = None,
    e2e_passed: bool = True,
    scenario_testing_passed: bool = True,
    kill_switch_test_passed: bool = True,
    metadata: dict[str, Any] | None = None,
) -> TestnetSessionPlan:
    config = load_testnet_session_plan_config()

    return TestnetSessionPlan(
        session_name=session_name or config.session_name,
        symbol=symbol or config.symbol,
        timeframe=timeframe or config.timeframe,
        dry_run=config.dry_run if dry_run is None else dry_run,
        max_notional_usd=config.max_notional_usd,
        max_margin_usd=config.max_margin_usd,
        max_leverage=config.max_leverage,
        e2e_passed=e2e_passed,
        scenario_testing_passed=scenario_testing_passed,
        kill_switch_test_passed=kill_switch_test_passed,
        reconciliation_required=config.require_reconciliation,
        planned_steps=[
            "validate_runtime_context",
            "validate_testnet_credentials_readiness",
            "run_preflight_quality_gate",
            "submit_dry_run_order_plan",
            "validate_order_lifecycle",
            "monitor_fills_and_rejections",
            "reconcile_portfolio",
            "generate_acceptance_report",
        ],
        metadata=metadata or {},
    )


def evaluate_testnet_session_plan(
    *,
    plan: TestnetSessionPlan | dict[str, Any],
    config: TestnetSessionPlanConfig | None = None,
) -> TestnetSessionPlanReport:
    resolved_config = config or load_testnet_session_plan_config()
    parsed = plan if isinstance(plan, TestnetSessionPlan) else TestnetSessionPlan.model_validate(plan)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if not parsed.dry_run:
        warnings.append("testnet_plan_not_dry_run")
        recommendations.append("Para V1, manter testnet em dry-run até acceptance completo.")

    if parsed.max_notional_usd > resolved_config.max_notional_usd:
        blockers.append("max_notional_above_testnet_limit")

    if parsed.max_margin_usd > resolved_config.max_margin_usd:
        blockers.append("max_margin_above_testnet_limit")

    if parsed.max_leverage > resolved_config.max_leverage:
        blockers.append("max_leverage_above_testnet_limit")

    if resolved_config.require_e2e and not parsed.e2e_passed:
        blockers.append("e2e_not_passed")

    if resolved_config.require_scenario_testing and not parsed.scenario_testing_passed:
        blockers.append("scenario_testing_not_passed")

    if resolved_config.require_kill_switch and not parsed.kill_switch_test_passed:
        blockers.append("kill_switch_test_not_passed")

    if resolved_config.require_reconciliation and not parsed.reconciliation_required:
        blockers.append("reconciliation_not_required_in_plan")

    if not parsed.planned_steps:
        blockers.append("planned_steps_missing")

    passed = not blockers

    return TestnetSessionPlanReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        blockers=blockers,
        warnings=warnings,
        recommendations=recommendations,
        plan=parsed.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_testnet_session_plan_report(
    report: TestnetSessionPlanReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_session_plan_report",
) -> Path:
    config = load_testnet_session_plan_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path