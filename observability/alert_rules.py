from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from observability.metrics_registry import MetricsSnapshot, metric_value, normalize_metric_name


load_dotenv()


AlertSeverity = Literal["INFO", "WARNING", "HIGH", "CRITICAL"]
AlertOperator = Literal["gt", "gte", "lt", "lte", "eq", "ne"]


class AlertRule(BaseModel):
    model_config = ConfigDict(extra="allow")

    rule_id: str
    metric_name: str
    operator: AlertOperator
    threshold: float
    severity: AlertSeverity = "WARNING"

    description: str = ""
    enabled: bool = True
    labels: dict[str, str] = Field(default_factory=dict)
    runbook: str | None = None


class AlertEvaluation(BaseModel):
    model_config = ConfigDict(extra="allow")

    rule_id: str
    metric_name: str
    fired: bool
    severity: AlertSeverity

    value: float | None = None
    threshold: float
    operator: AlertOperator

    message: str
    runbook: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class AlertEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "alert_rules"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    rules_count: int
    fired_count: int
    critical_count: int
    high_count: int
    warning_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    evaluations: list[dict[str, Any]] = Field(default_factory=list)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def compare(value: float, operator: AlertOperator, threshold: float) -> bool:
    if operator == "gt":
        return value > threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    if operator == "lte":
        return value <= threshold
    if operator == "eq":
        return value == threshold
    if operator == "ne":
        return value != threshold

    return False


def evaluate_alert_rule(
    *,
    rule: AlertRule | dict[str, Any],
    snapshot: MetricsSnapshot | dict[str, Any],
) -> AlertEvaluation:
    parsed_rule = rule if isinstance(rule, AlertRule) else AlertRule.model_validate(rule)

    if not parsed_rule.enabled:
        return AlertEvaluation(
            rule_id=parsed_rule.rule_id,
            metric_name=normalize_metric_name(parsed_rule.metric_name),
            fired=False,
            severity=parsed_rule.severity,
            value=None,
            threshold=parsed_rule.threshold,
            operator=parsed_rule.operator,
            message="Rule disabled.",
            runbook=parsed_rule.runbook,
            labels=parsed_rule.labels,
        )

    value = metric_value(snapshot, parsed_rule.metric_name)

    if value is None:
        return AlertEvaluation(
            rule_id=parsed_rule.rule_id,
            metric_name=normalize_metric_name(parsed_rule.metric_name),
            fired=False,
            severity=parsed_rule.severity,
            value=None,
            threshold=parsed_rule.threshold,
            operator=parsed_rule.operator,
            message="Metric not found.",
            runbook=parsed_rule.runbook,
            labels=parsed_rule.labels,
        )

    fired = compare(value, parsed_rule.operator, parsed_rule.threshold)

    return AlertEvaluation(
        rule_id=parsed_rule.rule_id,
        metric_name=normalize_metric_name(parsed_rule.metric_name),
        fired=fired,
        severity=parsed_rule.severity,
        value=value,
        threshold=parsed_rule.threshold,
        operator=parsed_rule.operator,
        message=parsed_rule.description or f"{parsed_rule.metric_name} {parsed_rule.operator} {parsed_rule.threshold}",
        runbook=parsed_rule.runbook,
        labels=parsed_rule.labels,
    )


def default_alert_rules() -> list[AlertRule]:
    return [
        AlertRule(
            rule_id="live_rejection_rate_high",
            metric_name="live_performance_rejection_rate",
            operator="gt",
            threshold=0.10,
            severity="HIGH",
            description="Taxa de rejeição de ordens acima do limite.",
            runbook="docs/INCIDENT_RESPONSE_RUNBOOK.md#order-rejections",
        ),
        AlertRule(
            rule_id="live_fill_rate_low",
            metric_name="live_performance_fill_rate",
            operator="lt",
            threshold=0.60,
            severity="WARNING",
            description="Fill rate abaixo do esperado.",
            runbook="docs/INCIDENT_RESPONSE_RUNBOOK.md#low-fill-rate",
        ),
        AlertRule(
            rule_id="risk_critical_findings",
            metric_name="live_risk_audit_critical_findings_count",
            operator="gt",
            threshold=0,
            severity="CRITICAL",
            description="Live risk audit encontrou finding crítico.",
            runbook="docs/INCIDENT_RESPONSE_RUNBOOK.md#risk-critical",
        ),
        AlertRule(
            rule_id="model_ood_rate_high",
            metric_name="live_drift_ood_rate",
            operator="gt",
            threshold=0.20,
            severity="HIGH",
            description="Taxa OOD do modelo acima do limite.",
            runbook="docs/INCIDENT_RESPONSE_RUNBOOK.md#model-drift",
        ),
        AlertRule(
            rule_id="production_guard_failed",
            metric_name="production_guard_blocking_fail_count",
            operator="gt",
            threshold=0,
            severity="CRITICAL",
            description="Production guard falhou.",
            runbook="docs/INCIDENT_RESPONSE_RUNBOOK.md#production-guard",
        ),
    ]


def evaluate_alert_rules(
    *,
    snapshot: MetricsSnapshot | dict[str, Any],
    rules: list[AlertRule | dict[str, Any]] | None = None,
    require_zero_critical: bool | None = None,
) -> AlertEvaluationReport:
    resolved_rules = rules or default_alert_rules()
    evaluations = [
        evaluate_alert_rule(rule=rule, snapshot=snapshot)
        for rule in resolved_rules
    ]

    fired = [item for item in evaluations if item.fired]
    critical = [item for item in fired if item.severity == "CRITICAL"]
    high = [item for item in fired if item.severity == "HIGH"]
    warning = [item for item in fired if item.severity == "WARNING"]

    resolved_require_zero_critical = (
        env_bool("ALERT_RULES_REQUIRE_ZERO_CRITICAL", True)
        if require_zero_critical is None
        else require_zero_critical
    )

    blockers = [item.rule_id for item in critical] if resolved_require_zero_critical else []
    warnings = [item.rule_id for item in high + warning]

    passed = not blockers

    return AlertEvaluationReport(
        passed=passed,
        status="PASS" if not fired else "WARN" if passed else "FAIL",
        rules_count=len(evaluations),
        fired_count=len(fired),
        critical_count=len(critical),
        high_count=len(high),
        warning_count=len(warning),
        blockers=blockers,
        warnings=warnings,
        evaluations=[item.model_dump(mode="json") for item in evaluations],
    )


def export_alert_evaluation_report(
    report: AlertEvaluationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "alert_evaluation_latest",
) -> Path:
    path = Path(output_dir or os.getenv("ALERT_RULES_OUTPUT_DIR", "artifacts/observability"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path