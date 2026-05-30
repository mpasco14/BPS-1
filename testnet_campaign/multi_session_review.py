from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from testnet_campaign.campaign_models import export_campaign_json


ReviewStatus = Literal["PASS", "WARN", "FAIL"]
ReviewDecision = Literal["READY_FOR_NEXT_GATE", "HOLD", "BLOCKED"]


class MultiSessionReviewReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "multi_session_testnet_review"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ReviewStatus
    passed: bool
    decision: ReviewDecision

    sessions_count: int
    passed_sessions: int
    warning_sessions: int
    failed_sessions: int

    total_iterations: int
    total_rejections: int
    total_fills: int
    total_final_flat: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    sessions: list[dict[str, Any]] = Field(default_factory=list)


def load_campaign_report(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    return json.loads(target.read_text(encoding="utf-8"))


def build_multi_session_review(
    *,
    report_paths: list[str | Path],
) -> MultiSessionReviewReport:
    sessions: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    for item in report_paths:
        path = Path(item)

        if not path.exists():
            blockers.append(f"session_report_missing:{path}")
            continue

        report = load_campaign_report(path)
        report["artifact_path"] = str(path)
        sessions.append(report)

    sessions_count = len(sessions)
    passed_sessions = sum(1 for item in sessions if item.get("passed") is True)
    warning_sessions = sum(1 for item in sessions if item.get("status") == "WARN")
    failed_sessions = sessions_count - passed_sessions

    total_iterations = sum(int(item.get("iterations_count", 0)) for item in sessions)
    total_rejections = sum(int(item.get("rejection_count", 0)) for item in sessions)
    total_fills = sum(int(item.get("fill_count", 0)) for item in sessions)
    total_final_flat = sum(int(item.get("final_flat_count", 0)) for item in sessions)

    for session in sessions:
        name = session.get("campaign_name", "unknown_session")

        if not session.get("passed", False):
            blockers.append(f"session_not_passed:{name}")

        if session.get("decision") != "PROMOTE":
            warnings.append(f"session_not_promoted:{name}")

        for blocker in session.get("blockers", []) or []:
            blockers.append(f"{name}:{blocker}")

        for warning in session.get("warnings", []) or []:
            warnings.append(f"{name}:{warning}")

    if total_rejections > 0:
        blockers.append("rejection_detected_across_sessions")

    if total_final_flat != total_iterations:
        blockers.append("not_all_iterations_final_flat_across_sessions")

    recommendations.append("Avançar para micro-live somente após múltiplas sessões reais testnet aprovadas.")
    recommendations.append("Revisar artifacts para garantir api_key/api_secret/signature mascarados.")
    recommendations.append("Manter aumento gradual: 30min → 2h → 6h → 12h.")

    passed = not blockers

    if passed and warnings:
        status = "WARN"
        decision = "HOLD"
    elif passed:
        status = "PASS"
        decision = "READY_FOR_NEXT_GATE"
    else:
        status = "FAIL"
        decision = "BLOCKED"

    return MultiSessionReviewReport(
        status=status,
        passed=passed,
        decision=decision,
        sessions_count=sessions_count,
        passed_sessions=passed_sessions,
        warning_sessions=warning_sessions,
        failed_sessions=failed_sessions,
        total_iterations=total_iterations,
        total_rejections=total_rejections,
        total_fills=total_fills,
        total_final_flat=total_final_flat,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        sessions=sessions,
    )


def export_multi_session_review_report(
    report: MultiSessionReviewReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "multi_session_testnet_review",
) -> Path:
    return export_campaign_json(
        report,
        output_dir=output_dir or "artifacts/testnet_campaign",
        name=name,
    )