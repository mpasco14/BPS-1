from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from testnet_readiness.testnet_fill_monitoring import TestnetFillMonitorReport
from testnet_readiness.testnet_order_lifecycle import TestnetOrderLifecycleReport
from testnet_readiness.testnet_portfolio_reconciliation import TestnetPortfolioReconciliationReport
from testnet_readiness.testnet_reconciliation_engine import TestnetReconciliationEngineReport
from testnet_readiness.testnet_session_plan import TestnetSessionPlanReport


load_dotenv()


AcceptanceStatus = Literal["ACCEPTED", "WARN", "REJECTED"]


class TestnetAcceptanceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_readiness")

    require_plan_pass: bool = True
    require_lifecycle_pass: bool = True
    require_fill_pass: bool = True
    require_portfolio_recon_pass: bool = True
    require_recon_engine_pass: bool = True


class TestnetAcceptanceReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_acceptance_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: AcceptanceStatus
    accepted: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    plan: dict[str, Any]
    lifecycle: dict[str, Any]
    fill_monitor: dict[str, Any]
    portfolio_reconciliation: dict[str, Any]
    reconciliation_engine: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_testnet_acceptance_config() -> TestnetAcceptanceConfig:
    return TestnetAcceptanceConfig(
        output_dir=Path(os.getenv("TESTNET_ACCEPTANCE_OUTPUT_DIR", "artifacts/testnet_readiness")),
        require_plan_pass=env_bool("TESTNET_ACCEPTANCE_REQUIRE_PLAN_PASS", True),
        require_lifecycle_pass=env_bool("TESTNET_ACCEPTANCE_REQUIRE_LIFECYCLE_PASS", True),
        require_fill_pass=env_bool("TESTNET_ACCEPTANCE_REQUIRE_FILL_PASS", True),
        require_portfolio_recon_pass=env_bool("TESTNET_ACCEPTANCE_REQUIRE_PORTFOLIO_RECON_PASS", True),
        require_recon_engine_pass=env_bool("TESTNET_ACCEPTANCE_REQUIRE_RECON_ENGINE_PASS", True),
    )


def build_testnet_acceptance_report(
    *,
    plan: TestnetSessionPlanReport | dict[str, Any],
    lifecycle: TestnetOrderLifecycleReport | dict[str, Any],
    fill_monitor: TestnetFillMonitorReport | dict[str, Any],
    portfolio_reconciliation: TestnetPortfolioReconciliationReport | dict[str, Any],
    reconciliation_engine: TestnetReconciliationEngineReport | dict[str, Any],
    config: TestnetAcceptanceConfig | None = None,
) -> TestnetAcceptanceReport:
    resolved_config = config or load_testnet_acceptance_config()

    parsed_plan = plan if isinstance(plan, TestnetSessionPlanReport) else TestnetSessionPlanReport.model_validate(plan)
    parsed_lifecycle = lifecycle if isinstance(lifecycle, TestnetOrderLifecycleReport) else TestnetOrderLifecycleReport.model_validate(lifecycle)
    parsed_fill = fill_monitor if isinstance(fill_monitor, TestnetFillMonitorReport) else TestnetFillMonitorReport.model_validate(fill_monitor)
    parsed_portfolio = portfolio_reconciliation if isinstance(portfolio_reconciliation, TestnetPortfolioReconciliationReport) else TestnetPortfolioReconciliationReport.model_validate(portfolio_reconciliation)
    parsed_engine = reconciliation_engine if isinstance(reconciliation_engine, TestnetReconciliationEngineReport) else TestnetReconciliationEngineReport.model_validate(reconciliation_engine)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved_config.require_plan_pass and not parsed_plan.passed:
        blockers.append("testnet_session_plan_not_passed")

    if resolved_config.require_lifecycle_pass and not parsed_lifecycle.passed:
        blockers.append("testnet_order_lifecycle_not_passed")

    if resolved_config.require_fill_pass and not parsed_fill.passed:
        blockers.append("testnet_fill_monitor_not_passed")

    if resolved_config.require_portfolio_recon_pass and not parsed_portfolio.passed:
        blockers.append("testnet_portfolio_reconciliation_not_passed")

    if resolved_config.require_recon_engine_pass and not parsed_engine.passed:
        blockers.append("testnet_reconciliation_engine_not_passed")

    warnings.extend([f"plan:{item}" for item in parsed_plan.warnings])
    warnings.extend([f"lifecycle:{item}" for item in parsed_lifecycle.warnings])
    warnings.extend([f"fill_monitor:{item}" for item in parsed_fill.warnings])
    warnings.extend([f"portfolio:{item}" for item in parsed_portfolio.warnings])
    warnings.extend([f"engine:{item}" for item in parsed_engine.warnings])

    recommendations.extend(parsed_plan.recommendations)
    recommendations.extend(parsed_engine.recommendations)

    if parsed_fill.rejection_rate > 0:
        recommendations.append("Não avançar para live enquanto houver rejeições não explicadas.")

    if parsed_portfolio.exchange_flat is False:
        recommendations.append("Sessão testnet deve encerrar flat na exchange.")

    accepted = not blockers

    return TestnetAcceptanceReport(
        status="ACCEPTED" if accepted and not warnings else "WARN" if accepted else "REJECTED",
        accepted=accepted,
        blockers=blockers,
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        plan=parsed_plan.model_dump(mode="json"),
        lifecycle=parsed_lifecycle.model_dump(mode="json"),
        fill_monitor=parsed_fill.model_dump(mode="json"),
        portfolio_reconciliation=parsed_portfolio.model_dump(mode="json"),
        reconciliation_engine=parsed_engine.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_testnet_acceptance_report(
    report: TestnetAcceptanceReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_acceptance_report",
) -> Path:
    config = load_testnet_acceptance_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path