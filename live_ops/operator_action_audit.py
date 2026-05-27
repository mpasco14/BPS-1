from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


OperatorActionStatus = Literal["REQUESTED", "APPROVED", "BLOCKED", "EXECUTED", "FAILED"]


class OperatorAuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live_ops")
    audit_log_file: Path = Path("artifacts/live_ops/operator_actions.jsonl")


class OperatorActionRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "operator_action_audit"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    action_id: str
    operator: str = "operator"
    command: str
    status: OperatorActionStatus

    environment: str = "development"
    session_name: str | None = None

    reason: str | None = None
    approved_by: str | None = None

    previous_hash: str | None = None
    action_hash: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class OperatorActionAuditReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "operator_action_audit_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    records_count: int
    valid_hash_chain: bool

    last_action_hash: str | None = None
    records: list[dict[str, Any]] = Field(default_factory=list)


def load_operator_audit_config() -> OperatorAuditConfig:
    return OperatorAuditConfig(
        output_dir=Path(os.getenv("OPERATOR_AUDIT_OUTPUT_DIR", "artifacts/live_ops")),
        audit_log_file=Path(os.getenv("OPERATOR_AUDIT_LOG_FILE", "artifacts/live_ops/operator_actions.jsonl")),
    )


def compute_action_hash(record: OperatorActionRecord, *, previous_hash: str | None = None) -> str:
    payload = record.model_dump(mode="json", exclude={"action_hash"})
    payload["previous_hash"] = previous_hash

    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def seal_operator_action_record(
    record: OperatorActionRecord,
    *,
    previous_hash: str | None = None,
) -> OperatorActionRecord:
    updated = record.model_copy(update={"previous_hash": previous_hash})
    action_hash = compute_action_hash(updated, previous_hash=previous_hash)

    return updated.model_copy(update={"action_hash": action_hash})


def append_operator_action_record(
    record: OperatorActionRecord,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_operator_audit_config()
    output_path = Path(path or config.audit_log_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_operator_action_records(output_path)
    previous_hash = existing[-1].action_hash if existing else None

    sealed = seal_operator_action_record(record, previous_hash=previous_hash)

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(sealed.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def load_operator_action_records(path: str | Path | None = None) -> list[OperatorActionRecord]:
    config = load_operator_audit_config()
    input_path = Path(path or config.audit_log_file)

    if not input_path.exists():
        return []

    records: list[OperatorActionRecord] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            records.append(OperatorActionRecord.model_validate(json.loads(line)))

    return records


def validate_hash_chain(records: list[OperatorActionRecord]) -> bool:
    previous_hash = None

    for record in records:
        if record.previous_hash != previous_hash:
            return False

        expected = compute_action_hash(record, previous_hash=previous_hash)

        if record.action_hash != expected:
            return False

        previous_hash = record.action_hash

    return True


def build_operator_action_audit_report(
    *,
    records: list[OperatorActionRecord] | None = None,
    path: str | Path | None = None,
) -> OperatorActionAuditReport:
    resolved_records = records if records is not None else load_operator_action_records(path)

    return OperatorActionAuditReport(
        records_count=len(resolved_records),
        valid_hash_chain=validate_hash_chain(resolved_records),
        last_action_hash=resolved_records[-1].action_hash if resolved_records else None,
        records=[item.model_dump(mode="json") for item in resolved_records],
    )


def export_operator_action_audit_report(
    report: OperatorActionAuditReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "operator_action_audit_latest",
) -> Path:
    config = load_operator_audit_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path