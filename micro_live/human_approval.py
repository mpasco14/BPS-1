from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live.common import env_bool, env_str, export_json


HumanApprovalStatus = Literal["PASS", "WARN", "FAIL"]


class HumanApprovalConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/micro_live")

    operator_name: str = ""
    approval_phrase: str = "I APPROVE MICRO LIVE"
    approval_text: str = ""

    require_human_approval: bool = True


class HumanApprovalReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_live_human_approval"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: HumanApprovalStatus
    passed: bool

    operator_name: str
    approval_phrase_required: str
    approval_text_present: bool
    approval_phrase_matched: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    config: dict[str, Any]


def load_human_approval_config() -> HumanApprovalConfig:
    return HumanApprovalConfig(
        output_dir=Path(os.getenv("MICRO_LIVE_OUTPUT_DIR", "artifacts/micro_live")),
        operator_name=env_str("MICRO_LIVE_OPERATOR_NAME"),
        approval_phrase=env_str("MICRO_LIVE_APPROVAL_PHRASE", "I APPROVE MICRO LIVE"),
        approval_text=env_str("MICRO_LIVE_APPROVAL_TEXT"),
        require_human_approval=env_bool("MICRO_LIVE_REQUIRE_HUMAN_APPROVAL", True),
    )


def evaluate_human_approval(
    *,
    config: HumanApprovalConfig | None = None,
) -> HumanApprovalReport:
    resolved = config or load_human_approval_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    approval_text_present = bool(resolved.approval_text.strip())
    approval_phrase_matched = resolved.approval_text.strip() == resolved.approval_phrase.strip()

    if resolved.require_human_approval and not resolved.operator_name:
        blockers.append("operator_name_required")

    if resolved.require_human_approval and not approval_text_present:
        blockers.append("human_approval_text_required")

    if resolved.require_human_approval and not approval_phrase_matched:
        blockers.append("human_approval_phrase_not_matched")

    recommendations.append("Aprovação humana deve ser explícita, registrada e não inferida.")
    recommendations.append("Não reutilizar aprovação antiga para nova sessão.")

    passed = not blockers

    return HumanApprovalReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        operator_name=resolved.operator_name,
        approval_phrase_required=resolved.approval_phrase,
        approval_text_present=approval_text_present,
        approval_phrase_matched=approval_phrase_matched,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        config={
            **resolved.model_dump(mode="json"),
            "approval_text": "***" if resolved.approval_text else "",
        },
    )


def export_human_approval_report(
    report: HumanApprovalReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "micro_live_human_approval",
) -> Path:
    resolved = load_human_approval_config()
    return export_json(report, output_dir=output_dir or resolved.output_dir, name=name)