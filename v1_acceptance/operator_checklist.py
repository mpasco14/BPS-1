from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ChecklistItemStatus = Literal["PENDING", "PASS", "FAIL", "WAIVED"]
ChecklistStatus = Literal["PASS", "WARN", "FAIL"]


class OperatorChecklistConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/v1_acceptance")

    require_evidence: bool = True
    require_approval: bool = True


class OperatorChecklistItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    item_id: str
    title: str
    category: str

    status: ChecklistItemStatus = "PENDING"

    required: bool = True
    evidence_path: str | None = None
    approved_by: str | None = None
    notes: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutableOperatorChecklist(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "v1_executable_operator_checklist"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    checklist_name: str = "v1_operator_checklist"
    operator: str = "operator"
    version: str = "1.0.0"

    items: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperatorChecklistReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "v1_operator_checklist_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ChecklistStatus
    passed: bool

    total_items: int
    required_items: int
    passed_items: int
    failed_items: int
    pending_items: int
    waived_items: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    checklist: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_operator_checklist_config() -> OperatorChecklistConfig:
    return OperatorChecklistConfig(
        output_dir=Path(os.getenv("V1_OPERATOR_CHECKLIST_OUTPUT_DIR", "artifacts/v1_acceptance")),
        require_evidence=env_bool("V1_OPERATOR_CHECKLIST_REQUIRE_EVIDENCE", True),
        require_approval=env_bool("V1_OPERATOR_CHECKLIST_REQUIRE_APPROVAL", True),
    )


def build_v1_operator_checklist(
    *,
    operator: str = "operator",
    version: str = "1.0.0",
    mark_demo_passed: bool = False,
) -> ExecutableOperatorChecklist:
    default_status: ChecklistItemStatus = "PASS" if mark_demo_passed else "PENDING"
    default_approval = operator if mark_demo_passed else None
    default_evidence = "artifacts/demo/evidence.json" if mark_demo_passed else None

    items = [
        OperatorChecklistItem(
            item_id="v1_scope_contract_reviewed",
            title="V1 Scope Contract revisado",
            category="contracts",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
        OperatorChecklistItem(
            item_id="v1_safety_contract_reviewed",
            title="V1 Safety Contract revisado",
            category="contracts",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
        OperatorChecklistItem(
            item_id="pytest_full_suite_passed",
            title="Suite completa de testes passou",
            category="quality",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
        OperatorChecklistItem(
            item_id="e2e_report_passed",
            title="E2E Full System Report aprovado",
            category="testing",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
        OperatorChecklistItem(
            item_id="scenario_testing_passed",
            title="Scenario Testing Report aprovado",
            category="testing",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
        OperatorChecklistItem(
            item_id="testnet_acceptance_passed",
            title="Testnet Acceptance Report aprovado",
            category="testnet",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
        OperatorChecklistItem(
            item_id="security_audit_passed",
            title="Security audit aprovado",
            category="security",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
        OperatorChecklistItem(
            item_id="kill_switch_tested",
            title="Kill switch testado",
            category="safety",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
        OperatorChecklistItem(
            item_id="reconciliation_confirmed",
            title="Reconciliação confirmada",
            category="reconciliation",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
        OperatorChecklistItem(
            item_id="live_disabled_for_v1",
            title="Live trading desabilitado por padrão na V1",
            category="live_safety",
            status=default_status,
            evidence_path=default_evidence,
            approved_by=default_approval,
        ),
    ]

    return ExecutableOperatorChecklist(
        operator=operator,
        version=version,
        items=[item.model_dump(mode="json") for item in items],
    )


def evaluate_operator_checklist(
    *,
    checklist: ExecutableOperatorChecklist | dict[str, Any],
    config: OperatorChecklistConfig | None = None,
) -> OperatorChecklistReport:
    resolved = config or load_operator_checklist_config()
    parsed = checklist if isinstance(checklist, ExecutableOperatorChecklist) else ExecutableOperatorChecklist.model_validate(checklist)
    items = [OperatorChecklistItem.model_validate(item) for item in parsed.items]

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    for item in items:
        if item.required and item.status == "PENDING":
            blockers.append(f"{item.item_id}:required_item_pending")

        if item.required and item.status == "FAIL":
            blockers.append(f"{item.item_id}:required_item_failed")

        if item.status == "WAIVED":
            warnings.append(f"{item.item_id}:item_waived")

        if resolved.require_evidence and item.required and item.status == "PASS" and not item.evidence_path:
            blockers.append(f"{item.item_id}:evidence_required")

        if resolved.require_approval and item.required and item.status == "PASS" and not item.approved_by:
            blockers.append(f"{item.item_id}:approval_required")

    required_items = [item for item in items if item.required]
    passed_items = sum(1 for item in items if item.status == "PASS")
    failed_items = sum(1 for item in items if item.status == "FAIL")
    pending_items = sum(1 for item in items if item.status == "PENDING")
    waived_items = sum(1 for item in items if item.status == "WAIVED")

    if pending_items:
        recommendations.append("Completar todos os itens obrigatórios antes de liberar a V1.")

    if failed_items:
        recommendations.append("Corrigir itens com FAIL antes de gerar V1 acceptance final.")

    passed = not blockers

    return OperatorChecklistReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        total_items=len(items),
        required_items=len(required_items),
        passed_items=passed_items,
        failed_items=failed_items,
        pending_items=pending_items,
        waived_items=waived_items,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        checklist=parsed.model_dump(mode="json"),
        config=resolved.model_dump(mode="json"),
    )


def export_operator_checklist_report(
    report: OperatorChecklistReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "v1_operator_checklist_report",
) -> Path:
    config = load_operator_checklist_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path