from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


StorageBackend = Literal["jsonl", "sqlite", "memory"]
StorageOperationStatus = Literal["OK", "NOT_FOUND", "ERROR"]


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/storage")
    default_backend: StorageBackend = "jsonl"
    records_dir: Path = Path("artifacts/storage/records")
    sqlite_db: Path = Path("artifacts/storage/local_storage.db")


class StorageRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    record_id: str
    collection: str

    payload: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    schema_version: str = "1.0"
    source: str = "storage_record"

    metadata: dict[str, Any] = Field(default_factory=dict)


class StorageQuery(BaseModel):
    model_config = ConfigDict(extra="allow")

    collection: str
    record_id: str | None = None
    limit: int = 100
    reverse: bool = False

    filters: dict[str, Any] = Field(default_factory=dict)


class StorageWriteResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "storage_write_result"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: StorageOperationStatus
    backend: StorageBackend
    collection: str
    record_id: str | None = None

    message: str = ""
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StorageReadResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "storage_read_result"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: StorageOperationStatus
    backend: StorageBackend
    collection: str

    record: dict[str, Any] | None = None
    records: list[dict[str, Any]] = Field(default_factory=list)

    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_storage_config() -> StorageConfig:
    backend = os.getenv("STORAGE_DEFAULT_BACKEND", "jsonl").strip().lower()

    if backend not in {"jsonl", "sqlite", "memory"}:
        backend = "jsonl"

    return StorageConfig(
        output_dir=Path(os.getenv("DATA_PERSISTENCE_OUTPUT_DIR", "artifacts/storage")),
        default_backend=backend,  # type: ignore[arg-type]
        records_dir=Path(os.getenv("STORAGE_RECORDS_DIR", "artifacts/storage/records")),
        sqlite_db=Path(os.getenv("STORAGE_SQLITE_DB", "artifacts/storage/local_storage.db")),
    )


def normalize_collection_name(collection: str) -> str:
    normalized = collection.strip().lower().replace(" ", "_").replace("/", "_").replace("\\", "_")

    if not normalized:
        return "default"

    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in normalized)


def stable_payload_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def generate_record_id(
    *,
    collection: str,
    payload: dict[str, Any],
    stable: bool = False,
) -> str:
    normalized_collection = normalize_collection_name(collection)

    if stable:
        return f"{normalized_collection}_{stable_payload_hash(payload)[:16]}"

    return f"{normalized_collection}_{uuid4().hex}"


def create_storage_record(
    *,
    collection: str,
    payload: dict[str, Any],
    record_id: str | None = None,
    stable_id: bool = False,
    source: str = "storage_record",
    schema_version: str = "1.0",
    metadata: dict[str, Any] | None = None,
) -> StorageRecord:
    normalized_collection = normalize_collection_name(collection)
    resolved_id = record_id or generate_record_id(
        collection=normalized_collection,
        payload=payload,
        stable=stable_id,
    )

    now = datetime.now(timezone.utc)

    return StorageRecord(
        record_id=resolved_id,
        collection=normalized_collection,
        payload=payload,
        created_at=now,
        updated_at=now,
        source=source,
        schema_version=schema_version,
        metadata=metadata or {},
    )


def record_matches_filters(record: StorageRecord, filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if key.startswith("metadata."):
            metadata_key = key.split(".", 1)[1]
            actual = record.metadata.get(metadata_key)
        elif key.startswith("payload."):
            payload_key = key.split(".", 1)[1]
            actual = record.payload.get(payload_key)
        else:
            actual = getattr(record, key, None)

        if actual != expected:
            return False

    return True


def storage_result_ok(
    *,
    backend: StorageBackend,
    collection: str,
    record_id: str | None = None,
    path: str | None = None,
    message: str = "OK",
    metadata: dict[str, Any] | None = None,
) -> StorageWriteResult:
    return StorageWriteResult(
        status="OK",
        backend=backend,
        collection=normalize_collection_name(collection),
        record_id=record_id,
        path=path,
        message=message,
        metadata=metadata or {},
    )


def storage_result_error(
    *,
    backend: StorageBackend,
    collection: str,
    message: str,
    record_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> StorageWriteResult:
    return StorageWriteResult(
        status="ERROR",
        backend=backend,
        collection=normalize_collection_name(collection),
        record_id=record_id,
        message=message,
        metadata=metadata or {},
    )