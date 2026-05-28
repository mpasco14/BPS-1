from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from data_persistence.storage_abstraction import (
    StorageQuery,
    StorageReadResult,
    StorageRecord,
    StorageWriteResult,
    create_storage_record,
    load_storage_config,
    normalize_collection_name,
    record_matches_filters,
    storage_result_error,
    storage_result_ok,
)


load_dotenv()


class JSONLRepository:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        config = load_storage_config()
        self.base_dir = Path(base_dir or os.getenv("JSONL_REPOSITORY_OUTPUT_DIR", str(config.records_dir)))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def collection_path(self, collection: str) -> Path:
        normalized = normalize_collection_name(collection)
        return self.base_dir / f"{normalized}.jsonl"

    def write_record(self, record: StorageRecord) -> StorageWriteResult:
        try:
            path = self.collection_path(record.collection)
            path.parent.mkdir(parents=True, exist_ok=True)

            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")

            return storage_result_ok(
                backend="jsonl",
                collection=record.collection,
                record_id=record.record_id,
                path=str(path),
                message="Record appended to JSONL repository.",
            )

        except OSError as exc:
            return storage_result_error(
                backend="jsonl",
                collection=record.collection,
                record_id=record.record_id,
                message=str(exc),
            )

    def create(
        self,
        *,
        collection: str,
        payload: dict[str, Any],
        record_id: str | None = None,
        stable_id: bool = False,
        source: str = "jsonl_repository",
        metadata: dict[str, Any] | None = None,
    ) -> StorageWriteResult:
        record = create_storage_record(
            collection=collection,
            payload=payload,
            record_id=record_id,
            stable_id=stable_id,
            source=source,
            metadata=metadata or {},
        )

        return self.write_record(record)

    def read_all(self, collection: str) -> list[StorageRecord]:
        path = self.collection_path(collection)

        if not path.exists():
            return []

        records: list[StorageRecord] = []

        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                records.append(StorageRecord.model_validate(json.loads(line)))

        return records

    def get(self, *, collection: str, record_id: str) -> StorageReadResult:
        normalized = normalize_collection_name(collection)

        for record in reversed(self.read_all(normalized)):
            if record.record_id == record_id:
                return StorageReadResult(
                    status="OK",
                    backend="jsonl",
                    collection=normalized,
                    record=record.model_dump(mode="json"),
                    message="Record found.",
                )

        return StorageReadResult(
            status="NOT_FOUND",
            backend="jsonl",
            collection=normalized,
            message="Record not found.",
        )

    def query(self, query: StorageQuery | dict[str, Any]) -> StorageReadResult:
        parsed = query if isinstance(query, StorageQuery) else StorageQuery.model_validate(query)
        normalized = normalize_collection_name(parsed.collection)

        records = self.read_all(normalized)

        if parsed.filters:
            records = [record for record in records if record_matches_filters(record, parsed.filters)]

        if parsed.record_id:
            records = [record for record in records if record.record_id == parsed.record_id]

        if parsed.reverse:
            records = list(reversed(records))

        limited = records[: max(0, parsed.limit)]

        return StorageReadResult(
            status="OK",
            backend="jsonl",
            collection=normalized,
            records=[record.model_dump(mode="json") for record in limited],
            message=f"{len(limited)} record(s) returned.",
            metadata={
                "total_matched": len(records),
                "limit": parsed.limit,
            },
        )


def build_jsonl_repository(base_dir: str | Path | None = None) -> JSONLRepository:
    return JSONLRepository(base_dir=base_dir)