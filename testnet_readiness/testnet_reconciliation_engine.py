from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from testnet_readiness.testnet_fill_monitoring import TestnetFillMonitorReport
from testnet_readiness.testnet_order_lifecycle import TestnetOrderLifecycleReport
from testnet_readiness.testnet_portfolio_reconciliation import TestnetPortfolioReconciliationReport


ReconEngineStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetReconciliationEngineReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_reconciliation_engine"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ReconEngineStatus
    passed: bool

    lifecycle_passed: bool
    fill_monitor_passed: bool
    portfolio_reconciliation_passed: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    lifecycle: dict[str, Any]
    fill_monitor: dict[str, Any]
    portfolio_reconciliation: dict[str, Any]


def run_testnet_reconciliation_engine(
    *,
    lifecycle: TestnetOrderLifecycleReport | dict[str, Any],
    fill_monitor: TestnetFillMonitorReport | dict[str, Any],
    portfolio_reconciliation: TestnetPortfolioReconciliationReport | dict[str, Any],
) -> TestnetReconciliationEngineReport:
    parsed_lifecycle = lifecycle if isinstance(lifecycle, TestnetOrderLifecycleReport) else TestnetOrderLifecycleReport.model_validate(lifecycle)
    parsed_fill = fill_monitor if isinstance(fill_monitor, TestnetFillMonitorReport) else TestnetFillMonitorReport.model_validate(fill_monitor)
    parsed_portfolio = portfolio_reconciliation if isinstance(portfolio_reconciliation, TestnetPortfolioReconciliationReport) else TestnetPortfolioReconciliationReport.model_validate(portfolio_reconciliation)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if not parsed_lifecycle.passed:
        blockers.append("order_lifecycle_not_passed")
        blockers.extend([f"lifecycle:{item}" for item in parsed_lifecycle.blockers])

    if not parsed_fill.passed:
        blockers.append("fill_monitor_not_passed")
        blockers.extend([f"fill_monitor:{item}" for item in parsed_fill.blockers])

    if not parsed_portfolio.passed:
        blockers.append("portfolio_reconciliation_not_passed")
        blockers.extend([f"portfolio:{item}" for item in parsed_portfolio.blockers])

    warnings.extend([f"lifecycle:{item}" for item in parsed_lifecycle.warnings])
    warnings.extend([f"fill_monitor:{item}" for item in parsed_fill.warnings])
    warnings.extend([f"portfolio:{item}" for item in parsed_portfolio.warnings])

    if parsed_lifecycle.rejected_count > 0:
        recommendations.append("Investigar rejeições antes de nova sessão testnet.")

    if parsed_fill.fill_rate < 1:
        recommendations.append("Comparar fill rate real com estimativas do backtest.")

    if not parsed_portfolio.exchange_flat:
        recommendations.append("Cancelar ordens e aguardar/zerar posição antes de encerrar teste.")

    passed = not blockers

    return TestnetReconciliationEngineReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        lifecycle_passed=parsed_lifecycle.passed,
        fill_monitor_passed=parsed_fill.passed,
        portfolio_reconciliation_passed=parsed_portfolio.passed,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        lifecycle=parsed_lifecycle.model_dump(mode="json"),
        fill_monitor=parsed_fill.model_dump(mode="json"),
        portfolio_reconciliation=parsed_portfolio.model_dump(mode="json"),
    )


def export_testnet_reconciliation_engine_report(
    report: TestnetReconciliationEngineReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_reconciliation_engine_report",
) -> Path:
    path = Path(output_dir or os.getenv("TESTNET_RECON_ENGINE_OUTPUT_DIR", "artifacts/testnet_readiness"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path