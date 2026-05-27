from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


DiffChangeType = Literal["added", "removed", "changed"]


class ConfigAuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/config")
    audit_log_file: Path = Path("artifacts/config/config_audit_log.jsonl")


class ConfigDiffEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    change_type: DiffChangeType

    old_value: Any | None = None
    new_value: Any | None = None


class ConfigDiffReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "config_diff_audit"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    changes_count: int
    added_count: int
    removed_count: int
    changed_count: int

    changes: list[dict[str, Any]] = Field(default_factory=list)


class ConfigAuditRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "config_audit_record"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    actor: str = "operator"
    reason: str
    environment: str = "development"

    diff: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_config_audit_config() -> ConfigAuditConfig:
    return ConfigAuditConfig(
        output_dir=Path(os.getenv("CONFIG_AUDIT_OUTPUT_DIR", "artifacts/config")),
        audit_log_file=Path(os.getenv("CONFIG_AUDIT_LOG_FILE", "artifacts/config/config_audit_log.jsonl")),
    )


def flatten_dict(payload: dict[str, Any], *, prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    for key, value in payload.items():
        normalized_key = f"{prefix}.{key}" if prefix else str(key)

        if isinstance(value, dict):
            flattened.update(flatten_dict(value, prefix=normalized_key))
        else:
            flattened[normalized_key] = value

    return flattened


def build_config_diff_report(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
) -> ConfigDiffReport:
    before_flat = flatten_dict(before)
    after_flat = flatten_dict(after)

    before_keys = set(before_flat.keys())
    after_keys = set(after_flat.keys())

    changes: list[ConfigDiffEntry] = []

    for key in sorted(after_keys - before_keys):
        changes.append(
            ConfigDiffEntry(
                key=key,
                change_type="added",
                new_value=after_flat[key],
            )
        )

    for key in sorted(before_keys - after_keys):
        changes.append(
            ConfigDiffEntry(
                key=key,
                change_type="removed",
                old_value=before_flat[key],
            )
        )

    for key in sorted(before_keys & after_keys):
        if before_flat[key] != after_flat[key]:
            changes.append(
                ConfigDiffEntry(
                    key=key,
                    change_type="changed",
                    old_value=before_flat[key],
                    new_value=after_flat[key],
                )
            )

    return ConfigDiffReport(
        changes_count=len(changes),
        added_count=sum(1 for item in changes if item.change_type == "added"),
        removed_count=sum(1 for item in changes if item.change_type == "removed"),
        changed_count=sum(1 for item in changes if item.change_type == "changed"),
        changes=[item.model_dump(mode="json") for item in changes],
    )


def append_config_audit_record(
    record: ConfigAuditRecord,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_config_audit_config()
    output_path = Path(path or config.audit_log_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def load_config_audit_records(path: str | Path | None = None) -> list[ConfigAuditRecord]:
    config = load_config_audit_config()
    input_path = Path(path or config.audit_log_file)

    if not input_path.exists():
        return []

    records: list[ConfigAuditRecord] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            records.append(ConfigAuditRecord.model_validate(json.loads(line)))

    return records


def export_config_diff_report(
    report: ConfigDiffReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "config_diff_latest",
) -> Path:
    config = load_config_audit_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path