from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "INVALID"]


class HumanApprovalConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/production")
    approvals_file: Path = Path("artifacts/production/human_approvals.jsonl")

    ttl_minutes: int = 60
    required_phrase: str = "I_APPROVE_CONTROLLED_LIVE_ACTIVATION"


class HumanApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    approval_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime

    requested_action: str
    requested_by: str = "system"
    approver: str | None = None

    reason: str
    risk_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    status: ApprovalStatus = "PENDING"


class HumanApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    approval_id: str
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    approver: str
    approved: bool
    confirmation_phrase: str
    comment: str | None = None


class HumanApprovalValidationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "human_approval_workflow"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    approval_id: str
    status: ApprovalStatus
    valid: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    request: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None
    approval_hash: str | None = None


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_human_approval_config() -> HumanApprovalConfig:
    return HumanApprovalConfig(
        output_dir=Path(os.getenv("HUMAN_APPROVAL_OUTPUT_DIR", "artifacts/production")),
        approvals_file=Path(os.getenv("HUMAN_APPROVAL_FILE", "artifacts/production/human_approvals.jsonl")),
        ttl_minutes=env_int("HUMAN_APPROVAL_TTL_MINUTES", 60),
        required_phrase=os.getenv(
            "HUMAN_APPROVAL_REQUIRED_PHRASE",
            "I_APPROVE_CONTROLLED_LIVE_ACTIVATION",
        ),
    )


def create_human_approval_request(
    *,
    approval_id: str,
    requested_action: str,
    reason: str,
    requested_by: str = "system",
    approver: str | None = None,
    risk_summary: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    config: HumanApprovalConfig | None = None,
) -> HumanApprovalRequest:
    resolved_config = config or load_human_approval_config()
    created_at = datetime.now(timezone.utc)

    return HumanApprovalRequest(
        approval_id=approval_id,
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=resolved_config.ttl_minutes),
        requested_action=requested_action,
        requested_by=requested_by,
        approver=approver,
        reason=reason,
        risk_summary=risk_summary or {},
        metadata=metadata or {},
    )


def approval_hash(
    request: HumanApprovalRequest,
    decision: HumanApprovalDecision,
) -> str:
    payload = {
        "approval_id": request.approval_id,
        "requested_action": request.requested_action,
        "approver": decision.approver,
        "approved": decision.approved,
        "decided_at": decision.decided_at.isoformat(),
    }

    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def validate_human_approval(
    *,
    request: HumanApprovalRequest | dict[str, Any],
    decision: HumanApprovalDecision | dict[str, Any],
    config: HumanApprovalConfig | None = None,
    now: datetime | None = None,
) -> HumanApprovalValidationReport:
    resolved_config = config or load_human_approval_config()
    resolved_request = request if isinstance(request, HumanApprovalRequest) else HumanApprovalRequest.model_validate(request)
    resolved_decision = decision if isinstance(decision, HumanApprovalDecision) else HumanApprovalDecision.model_validate(decision)

    current_time = now or datetime.now(timezone.utc)

    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    expires_at = resolved_request.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    blockers: list[str] = []
    warnings: list[str] = []

    if resolved_request.approval_id != resolved_decision.approval_id:
        blockers.append("approval_id_mismatch")

    if current_time > expires_at:
        blockers.append("approval_expired")

    if not resolved_decision.approved:
        blockers.append("approval_rejected")

    if resolved_decision.confirmation_phrase != resolved_config.required_phrase:
        blockers.append("confirmation_phrase_invalid")

    if resolved_request.approver and resolved_request.approver != resolved_decision.approver:
        blockers.append("approver_mismatch")

    valid = not blockers

    if valid:
        status: ApprovalStatus = "APPROVED"
    elif "approval_expired" in blockers:
        status = "EXPIRED"
    elif "approval_rejected" in blockers:
        status = "REJECTED"
    else:
        status = "INVALID"

    return HumanApprovalValidationReport(
        approval_id=resolved_request.approval_id,
        status=status,
        valid=valid,
        blockers=blockers,
        warnings=warnings,
        request=resolved_request.model_dump(mode="json"),
        decision=resolved_decision.model_dump(mode="json"),
        approval_hash=approval_hash(resolved_request, resolved_decision) if valid else None,
    )


def append_human_approval_record(
    record: HumanApprovalRequest | HumanApprovalValidationReport,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_human_approval_config()
    output_path = Path(path or config.approvals_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def load_human_approval_records(
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    config = load_human_approval_config()
    input_path = Path(path or config.approvals_file)

    if not input_path.exists():
        return []

    records: list[dict[str, Any]] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            records.append(json.loads(line))

    return records