from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from release_private.release_models import ComponentReport, PrivateReleaseConfig, export_release_json, load_private_release_config


class OperatorDailyChecklistInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    operator_name: str = ""
    read_runbook: bool = False
    git_clean_confirmed: bool = False
    env_checked: bool = False
    no_live_flags_confirmed: bool = False
    emergency_shutdown_ready: bool = False
    artifacts_dir_available: bool = False
    session_goal_defined: bool = False


def build_operator_daily_checklist(
    *,
    inputs: OperatorDailyChecklistInputs | dict[str, Any] | None = None,
    config: PrivateReleaseConfig | None = None,
) -> ComponentReport:
    resolved = config or load_private_release_config()
    parsed = (
        inputs
        if isinstance(inputs, OperatorDailyChecklistInputs)
        else OperatorDailyChecklistInputs.model_validate(inputs)
        if inputs is not None
        else OperatorDailyChecklistInputs(
            operator_name=resolved.operator_name,
            read_runbook=resolved.daily_checklist_confirmed,
            git_clean_confirmed=resolved.daily_checklist_confirmed,
            env_checked=resolved.daily_checklist_confirmed,
            no_live_flags_confirmed=resolved.daily_checklist_confirmed,
            emergency_shutdown_ready=resolved.daily_checklist_confirmed,
            artifacts_dir_available=resolved.daily_checklist_confirmed,
            session_goal_defined=resolved.daily_checklist_confirmed,
        )
    )

    blockers: list[str] = []
    recommendations: list[str] = []

    checks = parsed.model_dump(mode="json")
    checks.pop("operator_name", None)

    if not parsed.operator_name:
        blockers.append("operator_name_required")

    for name, value in checks.items():
        if value is not True:
            blockers.append(f"daily_check_not_confirmed:{name}")

    recommendations.append("Checklist diário deve ser preenchido antes de qualquer sessão testnet/live.")
    recommendations.append("Sem objetivo de sessão definido, não operar.")

    passed = not blockers

    return ComponentReport(
        source="private_release_operator_daily_checklist",
        status="PASS" if passed else "FAIL",
        passed=passed,
        blockers=sorted(set(blockers)),
        warnings=[],
        recommendations=sorted(set(recommendations)),
        metadata=parsed.model_dump(mode="json"),
    )


def export_operator_daily_checklist_report(
    report: ComponentReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "private_release_operator_daily_checklist",
) -> Path:
    return export_release_json(report, output_dir=output_dir, name=name)