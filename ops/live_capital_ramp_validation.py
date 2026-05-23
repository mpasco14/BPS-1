from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ops.live_performance_analyzer import LivePerformanceReport
from ops.live_risk_audit import LiveRiskAuditReport
from ops.strategy_health import StrategyHealthReport


load_dotenv()


CapitalRampAction = Literal[
    "ADVANCE_RECOMMENDED",
    "HOLD_LEVEL",
    "REDUCE_LEVEL",
    "PAUSE_LIVE",
    "MANUAL_REVIEW",
]


class LiveCapitalRampValidationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live")

    min_trades: int = 20
    min_net_pnl_usd: float = 0.0
    min_fill_rate: float = 0.60
    max_rejection_rate: float = 0.10
    max_drawdown_usd: float = 5.0
    min_strategy_health_score: float = 0.70
    max_critical_risk_findings: int = 0

    require_performance_pass: bool = True
    require_risk_audit_pass: bool = True


class LiveCapitalRampValidationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_capital_ramp_validation"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str
    action: CapitalRampAction
    passed: bool

    advance_recommended: bool = False
    capital_increase_allowed: bool = False

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    metrics: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, Any] | None = None
    risk_audit: dict[str, Any] | None = None
    strategy_health: dict[str, Any] | None = None
    config: dict[str, Any] = Field(default_factory=dict)


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


def load_live_capital_ramp_validation_config() -> LiveCapitalRampValidationConfig:
    return LiveCapitalRampValidationConfig(
        output_dir=Path(os.getenv("LIVE_CAPITAL_RAMP_OUTPUT_DIR", "artifacts/live")),
        min_trades=env_int("LIVE_CAPITAL_RAMP_MIN_TRADES", 20),
        min_net_pnl_usd=env_float("LIVE_CAPITAL_RAMP_MIN_NET_PNL_USD", 0),
        min_fill_rate=env_float("LIVE_CAPITAL_RAMP_MIN_FILL_RATE", 0.60),
        max_rejection_rate=env_float("LIVE_CAPITAL_RAMP_MAX_REJECTION_RATE", 0.10),
        max_drawdown_usd=env_float("LIVE_CAPITAL_RAMP_MAX_DRAWDOWN_USD", 5),
        min_strategy_health_score=env_float("LIVE_CAPITAL_RAMP_MIN_STRATEGY_HEALTH_SCORE", 0.70),
        max_critical_risk_findings=env_int("LIVE_CAPITAL_RAMP_MAX_CRITICAL_RISK_FINDINGS", 0),
        require_performance_pass=env_bool("LIVE_CAPITAL_RAMP_REQUIRE_PERFORMANCE_PASS", True),
        require_risk_audit_pass=env_bool("LIVE_CAPITAL_RAMP_REQUIRE_RISK_AUDIT_PASS", True),
    )


def build_live_capital_ramp_validation_report(
    *,
    performance: LivePerformanceReport | dict[str, Any],
    risk_audit: LiveRiskAuditReport | dict[str, Any],
    strategy_health: StrategyHealthReport | dict[str, Any] | None = None,
    config: LiveCapitalRampValidationConfig | None = None,
) -> LiveCapitalRampValidationReport:
    resolved_config = config or load_live_capital_ramp_validation_config()

    perf = performance if isinstance(performance, LivePerformanceReport) else LivePerformanceReport.model_validate(performance)
    audit = risk_audit if isinstance(risk_audit, LiveRiskAuditReport) else LiveRiskAuditReport.model_validate(risk_audit)

    health = None
    if strategy_health is not None:
        health = strategy_health if isinstance(strategy_health, StrategyHealthReport) else StrategyHealthReport.model_validate(strategy_health)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved_config.require_performance_pass and not perf.passed:
        blockers.append("live_performance_not_passed")

    if resolved_config.require_risk_audit_pass and not audit.passed:
        blockers.append("live_risk_audit_not_passed")

    if perf.filled_count < resolved_config.min_trades:
        warnings.append("trades_below_ramp_minimum")
        recommendations.append("Continuar no mesmo nível até coletar mais trades.")

    if perf.net_pnl_usd < resolved_config.min_net_pnl_usd:
        warnings.append("net_pnl_below_minimum")
        recommendations.append("Não avançar capital enquanto PnL líquido estiver abaixo do mínimo.")

    if perf.fill_rate < resolved_config.min_fill_rate:
        warnings.append("fill_rate_below_ramp_minimum")
        recommendations.append("Revisar execução, preço limite e cancelamento antes de avançar.")

    if perf.rejection_rate > resolved_config.max_rejection_rate:
        blockers.append("rejection_rate_above_ramp_limit")
        recommendations.append("Pausar avanço e auditar rejeições da Binance.")

    if perf.max_drawdown_usd > resolved_config.max_drawdown_usd:
        blockers.append("drawdown_above_ramp_limit")
        recommendations.append("Reduzir risco ou pausar micro-live até entender o drawdown.")

    if audit.critical_findings_count > resolved_config.max_critical_risk_findings:
        blockers.append("critical_risk_findings_above_limit")
        recommendations.append("Pausar live até zerar findings críticos.")

    if health is not None and health.health_score < resolved_config.min_strategy_health_score:
        warnings.append("strategy_health_below_ramp_minimum")
        recommendations.append("Manter capital atual e revisar estratégia antes de avançar.")

    metrics = {
        "filled_count": perf.filled_count,
        "net_pnl_usd": perf.net_pnl_usd,
        "fill_rate": perf.fill_rate,
        "rejection_rate": perf.rejection_rate,
        "max_drawdown_usd": perf.max_drawdown_usd,
        "risk_audit_passed": audit.passed,
        "critical_risk_findings": audit.critical_findings_count,
        "strategy_health_score": health.health_score if health else None,
    }

    if blockers:
        action: CapitalRampAction = "PAUSE_LIVE"
        passed = False
    elif warnings:
        action = "HOLD_LEVEL"
        passed = True
    else:
        action = "ADVANCE_RECOMMENDED"
        passed = True
        recommendations.append("Avanço recomendado para revisão manual; não aumentar capital automaticamente.")

    return LiveCapitalRampValidationReport(
        session_name=perf.session_name,
        action=action,
        passed=passed,
        advance_recommended=action == "ADVANCE_RECOMMENDED",
        capital_increase_allowed=False,
        blockers=blockers,
        warnings=warnings,
        recommendations=recommendations,
        metrics=metrics,
        performance=perf.model_dump(mode="json"),
        risk_audit=audit.model_dump(mode="json"),
        strategy_health=health.model_dump(mode="json") if health else None,
        config=resolved_config.model_dump(mode="json"),
    )


def export_live_capital_ramp_validation_report(
    report: LiveCapitalRampValidationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "live_capital_ramp_validation_latest",
) -> Path:
    config = load_live_capital_ramp_validation_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path