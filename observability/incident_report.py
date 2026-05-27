from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from observability.alert_rules import AlertEvaluationReport
from observability.metrics_registry import MetricsSnapshot


load_dotenv()


IncidentSeverity = Literal["NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


class IncidentReportConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/observability")
    severity_critical_threshold: int = 1
    severity_high_threshold: int = 3


class IncidentAction(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: str
    priority: str = "P1"
    owner: str = "operator"
    reason: str


class IncidentReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "incident_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    incident_id: str
    severity: IncidentSeverity
    active: bool

    title: str
    summary: str

    fired_alerts_count: int = 0
    critical_alerts_count: int = 0
    high_alerts_count: int = 0
    warning_alerts_count: int = 0

    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)

    alerts: list[dict[str, Any]] = Field(default_factory=list)
    metrics_snapshot: dict[str, Any] | None = None
    context: dict[str, Any] = Field(default_factory=dict)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_incident_report_config() -> IncidentReportConfig:
    return IncidentReportConfig(
        output_dir=Path(os.getenv("INCIDENT_REPORT_OUTPUT_DIR", "artifacts/observability")),
        severity_critical_threshold=env_int("INCIDENT_REPORT_SEVERITY_CRITICAL_THRESHOLD", 1),
        severity_high_threshold=env_int("INCIDENT_REPORT_SEVERITY_HIGH_THRESHOLD", 3),
    )


def severity_from_alerts(
    *,
    critical_count: int,
    high_count: int,
    warning_count: int,
    config: IncidentReportConfig,
) -> IncidentSeverity:
    if critical_count >= config.severity_critical_threshold:
        return "CRITICAL"

    if high_count >= config.severity_high_threshold:
        return "HIGH"

    if high_count > 0:
        return "MEDIUM"

    if warning_count > 0:
        return "LOW"

    return "NONE"


def actions_for_alerts(alerts: list[dict[str, Any]]) -> list[IncidentAction]:
    actions: list[IncidentAction] = []

    fired_rule_ids = {alert.get("rule_id") for alert in alerts if alert.get("fired")}

    if "risk_critical_findings" in fired_rule_ids:
        actions.append(
            IncidentAction(
                action="pause_live_and_run_risk_audit",
                priority="P0",
                reason="Risk audit crítico detectado.",
            )
        )

    if "production_guard_failed" in fired_rule_ids:
        actions.append(
            IncidentAction(
                action="block_live_activation",
                priority="P0",
                reason="Production guard falhou.",
            )
        )

    if "model_ood_rate_high" in fired_rule_ids:
        actions.append(
            IncidentAction(
                action="switch_model_to_watch_mode",
                priority="P1",
                reason="OOD rate acima do limite.",
            )
        )

    if "live_rejection_rate_high" in fired_rule_ids:
        actions.append(
            IncidentAction(
                action="inspect_exchange_rejections_and_reduce_order_flow",
                priority="P1",
                reason="Taxa de rejeição de ordens elevada.",
            )
        )

    if "live_fill_rate_low" in fired_rule_ids:
        actions.append(
            IncidentAction(
                action="review_limit_price_and_market_liquidity",
                priority="P2",
                reason="Fill rate baixo.",
            )
        )

    if not actions and fired_rule_ids:
        actions.append(
            IncidentAction(
                action="operator_review_required",
                priority="P2",
                reason="Alertas ativos exigem revisão manual.",
            )
        )

    return actions


def generate_incident_report(
    *,
    alert_report: AlertEvaluationReport | dict[str, Any],
    metrics_snapshot: MetricsSnapshot | dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    config: IncidentReportConfig | None = None,
) -> IncidentReport:
    resolved_config = config or load_incident_report_config()
    alerts = alert_report if isinstance(alert_report, AlertEvaluationReport) else AlertEvaluationReport.model_validate(alert_report)

    fired_alerts = [item for item in alerts.evaluations if item.get("fired")]

    severity = severity_from_alerts(
        critical_count=alerts.critical_count,
        high_count=alerts.high_count,
        warning_count=alerts.warning_count,
        config=resolved_config,
    )

    active = severity != "NONE"

    incident_id = f"incident_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    if active:
        title = f"Observability incident: {severity}"
        summary = f"{alerts.fired_count} alerta(s) ativo(s): {alerts.critical_count} critical, {alerts.high_count} high, {alerts.warning_count} warning."
    else:
        title = "No active incident"
        summary = "Nenhum alerta ativo no snapshot atual."

    snapshot_payload = None
    if metrics_snapshot is not None:
        snapshot_payload = (
            metrics_snapshot.model_dump(mode="json")
            if isinstance(metrics_snapshot, MetricsSnapshot)
            else MetricsSnapshot.model_validate(metrics_snapshot).model_dump(mode="json")
        )

    recommended_actions = [item.model_dump(mode="json") for item in actions_for_alerts(fired_alerts)]

    return IncidentReport(
        incident_id=incident_id,
        severity=severity,
        active=active,
        title=title,
        summary=summary,
        fired_alerts_count=alerts.fired_count,
        critical_alerts_count=alerts.critical_count,
        high_alerts_count=alerts.high_count,
        warning_alerts_count=alerts.warning_count,
        recommended_actions=recommended_actions,
        alerts=fired_alerts,
        metrics_snapshot=snapshot_payload,
        context=context or {},
    )


def export_incident_report(
    report: IncidentReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "incident_report_latest",
) -> Path:
    config = load_incident_report_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path