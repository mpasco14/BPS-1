from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


KeyRotationStatus = Literal["PASS", "WARN", "FAIL"]


class KeyRotationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/security")

    max_age_days: int = 30
    warn_age_days: int = 21
    require_last_rotated: bool = True
    require_next_rotation: bool = True


class KeyRotationRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    key_name: str
    last_rotated_at: datetime | None = None
    next_rotation_due_at: datetime | None = None

    owner: str = "operator"
    environment: str = "development"

    rotation_procedure_doc: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KeyRotationFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: KeyRotationStatus
    message: str
    key_name: str
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class KeyRotationCheckReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "key_rotation_check"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: KeyRotationStatus

    keys_count: int
    findings_count: int
    blocking_findings_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    findings: list[dict[str, Any]] = Field(default_factory=list)
    keys: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_key_rotation_config() -> KeyRotationConfig:
    return KeyRotationConfig(
        output_dir=Path(os.getenv("KEY_ROTATION_OUTPUT_DIR", "artifacts/security")),
        max_age_days=env_int("KEY_ROTATION_MAX_AGE_DAYS", 30),
        warn_age_days=env_int("KEY_ROTATION_WARN_AGE_DAYS", 21),
        require_last_rotated=env_bool("KEY_ROTATION_REQUIRE_LAST_ROTATED", True),
        require_next_rotation=env_bool("KEY_ROTATION_REQUIRE_NEXT_ROTATION", True),
    )


def days_between(start: datetime, end: datetime) -> float:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    return (end - start).total_seconds() / 86400


def rotation_finding(
    *,
    code: str,
    status: KeyRotationStatus,
    message: str,
    key_name: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> KeyRotationFinding:
    return KeyRotationFinding(
        code=code,
        status=status,
        message=message,
        key_name=key_name,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def audit_key_rotation_record(
    record: KeyRotationRecord,
    *,
    config: KeyRotationConfig,
    now: datetime | None = None,
) -> list[KeyRotationFinding]:
    current_time = now or datetime.now(timezone.utc)
    findings: list[KeyRotationFinding] = []

    if config.require_last_rotated and record.last_rotated_at is None:
        findings.append(
            rotation_finding(
                code="last_rotated_missing",
                status="FAIL",
                message="Data de última rotação ausente.",
                key_name=record.key_name,
                expected="last_rotated_at",
                blocking=True,
            )
        )

    if config.require_next_rotation and record.next_rotation_due_at is None:
        findings.append(
            rotation_finding(
                code="next_rotation_due_missing",
                status="WARN",
                message="Data da próxima rotação ausente.",
                key_name=record.key_name,
                expected="next_rotation_due_at",
                blocking=False,
            )
        )

    if record.last_rotated_at is not None:
        age_days = days_between(record.last_rotated_at, current_time)

        if age_days > config.max_age_days:
            findings.append(
                rotation_finding(
                    code="key_rotation_overdue",
                    status="FAIL",
                    message="Chave acima da idade máxima permitida.",
                    key_name=record.key_name,
                    value=round(age_days, 2),
                    expected=f"<={config.max_age_days}",
                    blocking=True,
                )
            )
        elif age_days > config.warn_age_days:
            findings.append(
                rotation_finding(
                    code="key_rotation_warning_age",
                    status="WARN",
                    message="Chave próxima do prazo máximo de rotação.",
                    key_name=record.key_name,
                    value=round(age_days, 2),
                    expected=f"<={config.warn_age_days}",
                    blocking=False,
                )
            )

    if record.next_rotation_due_at is not None:
        due = record.next_rotation_due_at

        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)

        if current_time > due:
            findings.append(
                rotation_finding(
                    code="next_rotation_due_date_passed",
                    status="FAIL",
                    message="Data prevista para próxima rotação já passou.",
                    key_name=record.key_name,
                    value=due.isoformat(),
                    expected=f">={current_time.isoformat()}",
                    blocking=True,
                )
            )

    if not record.rotation_procedure_doc:
        findings.append(
            rotation_finding(
                code="rotation_procedure_doc_missing",
                status="WARN",
                message="Documento de procedimento de rotação ausente.",
                key_name=record.key_name,
                expected="docs/SECURITY.md",
                blocking=False,
            )
        )

    return findings


def build_key_rotation_check_report(
    *,
    keys: list[KeyRotationRecord | dict[str, Any]],
    config: KeyRotationConfig | None = None,
    now: datetime | None = None,
) -> KeyRotationCheckReport:
    resolved_config = config or load_key_rotation_config()

    parsed = [
        item if isinstance(item, KeyRotationRecord) else KeyRotationRecord.model_validate(item)
        for item in keys
    ]

    findings: list[KeyRotationFinding] = []

    for record in parsed:
        findings.extend(audit_key_rotation_record(record, config=resolved_config, now=now))

    blockers = [f"{item.key_name}:{item.code}" for item in findings if item.blocking]
    warnings = [f"{item.key_name}:{item.code}" for item in findings if item.status == "WARN"]

    passed = not blockers

    return KeyRotationCheckReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        keys_count=len(parsed),
        findings_count=len(findings),
        blocking_findings_count=len(blockers),
        blockers=blockers,
        warnings=warnings,
        findings=[item.model_dump(mode="json") for item in findings],
        keys=[item.model_dump(mode="json") for item in parsed],
        config=resolved_config.model_dump(mode="json"),
    )


def export_key_rotation_check_report(
    report: KeyRotationCheckReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "key_rotation_check_latest",
) -> Path:
    config = load_key_rotation_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path