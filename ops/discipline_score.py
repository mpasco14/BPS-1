from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
PolicyPillar = Literal["data_quality", "risk", "execution", "model", "governance", "security", "resilience"]


class DisciplinePolicyEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    pillar: PolicyPillar
    rule_code: str
    passed: bool
    severity: Severity = "MEDIUM"

    symbol: str = "BTCUSDT"
    timeframe: str | None = None

    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DisciplineScoreReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "discipline_score"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    discipline_score: float
    risk_compliance_score: float
    execution_compliance_score: float
    data_quality_compliance_score: float

    events_count: int
    violations_count: int
    critical_violations_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)


SEVERITY_WEIGHTS: dict[str, float] = {
    "LOW": 1.0,
    "MEDIUM": 2.0,
    "HIGH": 4.0,
    "CRITICAL": 8.0,
}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def score_events(events: list[DisciplinePolicyEvent], *, pillar: str | None = None) -> float:
    selected = [event for event in events if pillar is None or event.pillar == pillar]

    if not selected:
        return 1.0

    total_weight = sum(SEVERITY_WEIGHTS[event.severity] for event in selected)
    passed_weight = sum(SEVERITY_WEIGHTS[event.severity] for event in selected if event.passed)

    if total_weight <= 0:
        return 1.0

    return round(passed_weight / total_weight, 6)


def build_discipline_score_report(
    *,
    events: list[DisciplinePolicyEvent | dict[str, Any]],
    min_acceptable_score: float | None = None,
    blocking_threshold: float | None = None,
) -> DisciplineScoreReport:
    parsed_events = [
        event if isinstance(event, DisciplinePolicyEvent) else DisciplinePolicyEvent.model_validate(event)
        for event in events
    ]

    resolved_min = min_acceptable_score if min_acceptable_score is not None else env_float("DISCIPLINE_SCORE_MIN_ACCEPTABLE", 0.80)
    resolved_blocking = blocking_threshold if blocking_threshold is not None else env_float("DISCIPLINE_SCORE_BLOCKING_THRESHOLD", 0.60)

    discipline_score = score_events(parsed_events)
    risk_score = score_events(parsed_events, pillar="risk")
    execution_score = score_events(parsed_events, pillar="execution")
    data_quality_score = score_events(parsed_events, pillar="data_quality")

    violations = [event for event in parsed_events if not event.passed]
    critical_violations = [event for event in violations if event.severity == "CRITICAL"]

    blockers: list[str] = []
    warnings: list[str] = []

    if critical_violations:
        blockers.extend(event.rule_code for event in critical_violations)

    if discipline_score < resolved_blocking:
        blockers.append("discipline_score_below_blocking_threshold")
    elif discipline_score < resolved_min:
        warnings.append("discipline_score_below_acceptable_threshold")

    passed = not blockers and discipline_score >= resolved_min

    return DisciplineScoreReport(
        passed=passed,
        status="PASS" if passed else "FAIL" if blockers else "WARN",
        discipline_score=discipline_score,
        risk_compliance_score=risk_score,
        execution_compliance_score=execution_score,
        data_quality_compliance_score=data_quality_score,
        events_count=len(parsed_events),
        violations_count=len(violations),
        critical_violations_count=len(critical_violations),
        blockers=blockers,
        warnings=warnings,
        events=[event.model_dump(mode="json") for event in parsed_events],
    )


def export_discipline_score_report(
    report: DisciplineScoreReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "discipline_score_latest",
) -> Path:
    path = Path(output_dir or os.getenv("DISCIPLINE_SCORE_OUTPUT_DIR", "artifacts/governance"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path