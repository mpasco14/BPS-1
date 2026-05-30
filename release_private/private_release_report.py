from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from release_private.config_freeze import build_final_config_freeze_report
from release_private.evidence_pack import build_artifact_evidence_pack
from release_private.operator_daily_checklist import build_operator_daily_checklist
from release_private.release_lock import evaluate_release_lock
from release_private.release_models import ComponentReport, PrivateReleaseConfig, ReleaseDecision, ReleaseStatus, export_release_json, load_private_release_config
from release_private.runbooks_review import review_final_runbooks
from release_private.weekly_audit import build_weekly_audit_routine


class PrivateV1ReleaseReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "private_v1_release_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    release_name: str
    release_version: str

    status: ReleaseStatus
    passed: bool
    decision: ReleaseDecision

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    release_lock: dict[str, Any]
    config_freeze: dict[str, Any]
    runbooks_review: dict[str, Any]
    evidence_pack: dict[str, Any]
    operator_daily_checklist: dict[str, Any]
    weekly_audit: dict[str, Any]

    config: dict[str, Any]


def build_private_v1_release_report(
    *,
    release_lock: ComponentReport | dict[str, Any],
    config_freeze: ComponentReport | dict[str, Any],
    runbooks_review: ComponentReport | dict[str, Any],
    evidence_pack: ComponentReport | dict[str, Any],
    operator_daily_checklist: ComponentReport | dict[str, Any],
    weekly_audit: ComponentReport | dict[str, Any],
    config: PrivateReleaseConfig | None = None,
) -> PrivateV1ReleaseReport:
    resolved = config or load_private_release_config()

    components = {
        "release_lock": release_lock,
        "config_freeze": config_freeze,
        "runbooks_review": runbooks_review,
        "evidence_pack": evidence_pack,
        "operator_daily_checklist": operator_daily_checklist,
        "weekly_audit": weekly_audit,
    }

    parsed = {
        name: report if isinstance(report, ComponentReport) else ComponentReport.model_validate(report)
        for name, report in components.items()
    }

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    for name, report in parsed.items():
        if not report.passed:
            blockers.append(f"{name}_not_passed")
            blockers.extend([f"{name}:{item}" for item in report.blockers])

        warnings.extend([f"{name}:{item}" for item in report.warnings])
        recommendations.extend(report.recommendations)

    passed = not blockers

    if passed and warnings:
        status: ReleaseStatus = "WARN"
        decision: ReleaseDecision = "REVIEW_REQUIRED"
    elif passed:
        status = "PASS"
        decision = "READY_FOR_TAG"
    else:
        status = "FAIL"
        decision = "BLOCKED"

    recommendations.append("Criar tag somente quando decision=READY_FOR_TAG.")
    recommendations.append("Depois da tag, qualquer alteração exige nova tag ou release candidate.")

    return PrivateV1ReleaseReport(
        release_name=resolved.release_name,
        release_version=resolved.release_version,
        status=status,
        passed=passed,
        decision=decision,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        release_lock=parsed["release_lock"].model_dump(mode="json"),
        config_freeze=parsed["config_freeze"].model_dump(mode="json"),
        runbooks_review=parsed["runbooks_review"].model_dump(mode="json"),
        evidence_pack=parsed["evidence_pack"].model_dump(mode="json"),
        operator_daily_checklist=parsed["operator_daily_checklist"].model_dump(mode="json"),
        weekly_audit=parsed["weekly_audit"].model_dump(mode="json"),
        config=resolved.model_dump(mode="json"),
    )


def run_private_v1_release_freeze(
    *,
    tests_passed: bool = False,
    config: PrivateReleaseConfig | None = None,
) -> PrivateV1ReleaseReport:
    resolved = config or load_private_release_config()

    release_lock = evaluate_release_lock(config=resolved)
    release_lock.metadata["tests_passed"] = tests_passed

    if resolved.require_tests_passed and tests_passed:
        release_lock.blockers = [
            item for item in release_lock.blockers if item != "full_test_suite_not_confirmed"
        ]
        release_lock.passed = len(release_lock.blockers) == 0
        release_lock.status = "PASS" if release_lock.passed and not release_lock.warnings else "WARN" if release_lock.passed else "FAIL"

    config_freeze = build_final_config_freeze_report()
    runbooks = review_final_runbooks(config=resolved)
    evidence = build_artifact_evidence_pack(config=resolved)
    daily = build_operator_daily_checklist(config=resolved)
    weekly = build_weekly_audit_routine(config=resolved)

    return build_private_v1_release_report(
        release_lock=release_lock,
        config_freeze=config_freeze,
        runbooks_review=runbooks,
        evidence_pack=evidence,
        operator_daily_checklist=daily,
        weekly_audit=weekly,
        config=resolved,
    )


def export_private_v1_release_report(
    report: PrivateV1ReleaseReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "private_v1_release_report",
) -> Path:
    return export_release_json(report, output_dir=output_dir, name=name)