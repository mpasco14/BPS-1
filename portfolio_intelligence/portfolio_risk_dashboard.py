from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from portfolio_intelligence.exposure_concentration_guard import ExposureConcentrationReport
from portfolio_intelligence.exposure_ledger import ExposureLedgerSummary
from portfolio_intelligence.pnl_attribution import PnLAttributionReport
from portfolio_intelligence.position_lifecycle import PositionLifecycleReport


load_dotenv()


PortfolioRiskStatus = Literal["PASS", "WARN", "FAIL"]


class PortfolioRiskDashboard(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "portfolio_level_risk_dashboard"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: PortfolioRiskStatus
    passed: bool

    headline: dict[str, Any] = Field(default_factory=dict)
    exposure: dict[str, Any] = Field(default_factory=dict)
    positions: dict[str, Any] = Field(default_factory=dict)
    concentration: dict[str, Any] = Field(default_factory=dict)
    pnl_attribution: dict[str, Any] = Field(default_factory=dict)

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


def build_portfolio_risk_dashboard(
    *,
    summary: ExposureLedgerSummary | dict[str, Any],
    lifecycle: PositionLifecycleReport | dict[str, Any],
    concentration: ExposureConcentrationReport | dict[str, Any],
    pnl_attribution: PnLAttributionReport | dict[str, Any],
) -> PortfolioRiskDashboard:
    parsed_summary = summary if isinstance(summary, ExposureLedgerSummary) else ExposureLedgerSummary.model_validate(summary)
    parsed_lifecycle = lifecycle if isinstance(lifecycle, PositionLifecycleReport) else PositionLifecycleReport.model_validate(lifecycle)
    parsed_concentration = concentration if isinstance(concentration, ExposureConcentrationReport) else ExposureConcentrationReport.model_validate(concentration)
    parsed_pnl = pnl_attribution if isinstance(pnl_attribution, PnLAttributionReport) else PnLAttributionReport.model_validate(pnl_attribution)

    blockers = list(parsed_concentration.blockers)
    warnings = list(parsed_concentration.warnings)
    recommendations: list[str] = []

    if parsed_summary.total_abs_notional_usd <= 0:
        recommendations.append("Nenhuma exposição aberta detectada.")

    if parsed_lifecycle.open_positions_count > 0:
        recommendations.append("Monitorar posições abertas e reconciliar com a exchange.")

    if parsed_summary.realized_net_pnl_usd < 0:
        warnings.append("portfolio_realized_net_pnl_negative")
        recommendations.append("Revisar fontes com PnL negativo antes de aumentar risco.")

    if parsed_concentration.status == "FAIL":
        recommendations.append("Bloquear novas entradas até reduzir concentração.")
    elif parsed_concentration.status == "WARN":
        recommendations.append("Manter nível atual e revisar concentração por timeframe/direção.")

    passed = not blockers

    status: PortfolioRiskStatus = "PASS" if passed and not warnings else "WARN" if passed else "FAIL"

    return PortfolioRiskDashboard(
        status=status,
        passed=passed,
        headline={
            "total_abs_notional_usd": parsed_summary.total_abs_notional_usd,
            "net_notional_usd": parsed_summary.net_notional_usd,
            "total_margin_usd": parsed_summary.total_margin_usd,
            "realized_net_pnl_usd": parsed_summary.realized_net_pnl_usd,
            "open_positions_count": parsed_lifecycle.open_positions_count,
            "concentration_status": parsed_concentration.status,
        },
        exposure=parsed_summary.model_dump(mode="json"),
        positions=parsed_lifecycle.model_dump(mode="json"),
        concentration=parsed_concentration.model_dump(mode="json"),
        pnl_attribution=parsed_pnl.model_dump(mode="json"),
        blockers=blockers,
        warnings=warnings,
        recommendations=recommendations,
    )


def export_portfolio_risk_dashboard(
    dashboard: PortfolioRiskDashboard,
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or os.getenv("PORTFOLIO_RISK_DASHBOARD_FILE", "artifacts/portfolio/portfolio_risk_dashboard.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(dashboard.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path