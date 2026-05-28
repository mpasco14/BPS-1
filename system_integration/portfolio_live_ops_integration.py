from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


class PortfolioRiskInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_abs_notional_usd: float = 0.0
    net_notional_usd: float = 0.0
    total_margin_usd: float = 0.0
    open_positions_count: int = 0

    realized_net_pnl_usd: float = 0.0
    max_leverage_seen: int = 0

    concentration_status: str = "PASS"
    concentration_blockers: list[str] = Field(default_factory=list)
    concentration_warnings: list[str] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


class LiveOpsInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    safe_mode_active: bool = False
    kill_switch_active: bool = False

    supervisor_status: str = "RUNNING"
    supervisor_allowed_to_continue: bool = True
    supervisor_blockers: list[str] = Field(default_factory=list)
    supervisor_warnings: list[str] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioLiveOpsIntegrationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "portfolio_risk_live_ops_integration"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    allowed_to_continue: bool
    status: str

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)

    portfolio: dict[str, Any]
    live_ops: dict[str, Any]


def integrate_portfolio_risk_live_ops(
    *,
    portfolio: PortfolioRiskInput | dict[str, Any],
    live_ops: LiveOpsInput | dict[str, Any],
) -> PortfolioLiveOpsIntegrationReport:
    parsed_portfolio = portfolio if isinstance(portfolio, PortfolioRiskInput) else PortfolioRiskInput.model_validate(portfolio)
    parsed_live_ops = live_ops if isinstance(live_ops, LiveOpsInput) else LiveOpsInput.model_validate(live_ops)

    blockers: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []

    if parsed_portfolio.concentration_status == "FAIL":
        blockers.append("portfolio_concentration_failed")
        actions.append("block_new_entries_until_concentration_reduced")

    blockers.extend([f"portfolio:{item}" for item in parsed_portfolio.concentration_blockers])
    warnings.extend([f"portfolio:{item}" for item in parsed_portfolio.concentration_warnings])

    if parsed_portfolio.realized_net_pnl_usd < 0:
        warnings.append("portfolio_realized_net_pnl_negative")
        actions.append("review_pnl_attribution_before_increasing_risk")

    if parsed_live_ops.kill_switch_active:
        blockers.append("kill_switch_active")
        actions.append("cancel_open_orders_and_enter_safe_mode")

    if parsed_live_ops.safe_mode_active:
        warnings.append("safe_mode_active")
        actions.append("allow_reduce_only")

    if not parsed_live_ops.supervisor_allowed_to_continue:
        blockers.append("live_session_supervisor_blocked")
        actions.append("pause_session_and_review_supervisor_report")

    blockers.extend([f"supervisor:{item}" for item in parsed_live_ops.supervisor_blockers])
    warnings.extend([f"supervisor:{item}" for item in parsed_live_ops.supervisor_warnings])

    allowed = not blockers

    return PortfolioLiveOpsIntegrationReport(
        allowed_to_continue=allowed,
        status="PASS" if allowed and not warnings else "WARN" if allowed else "BLOCKED",
        blockers=blockers,
        warnings=warnings,
        recommended_actions=sorted(set(actions)),
        portfolio=parsed_portfolio.model_dump(mode="json"),
        live_ops=parsed_live_ops.model_dump(mode="json"),
    )


def export_portfolio_live_ops_integration_report(
    report: PortfolioLiveOpsIntegrationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "portfolio_live_ops_integration_latest",
) -> Path:
    path = Path(output_dir or os.getenv("PORTFOLIO_LIVE_OPS_OUTPUT_DIR", "artifacts/system_integration"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path