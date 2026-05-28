from __future__ import annotations

import json
import os
import sqlite3
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


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS records (
    collection TEXT NOT NULL,
    record_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    source TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (collection, record_id)
);

CREATE INDEX IF NOT EXISTS idx_records_collection_created_at
ON records(collection, created_at);
"""


class SQLiteRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        config = load_storage_config()
        self.db_path = Path(db_path or os.getenv("STORAGE_SQLITE_DB", str(config.sqlite_db)))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.commit()

    def write_record(self, record: StorageRecord) -> StorageWriteResult:
        try:
            with self.connect() as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO records (
                        collection,
                        record_id,
                        payload_json,
                        metadata_json,
                        source,
                        schema_version,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.collection,
                        record.record_id,
                        json.dumps(record.payload, ensure_ascii=False, sort_keys=True),
                        json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
                        record.source,
                        record.schema_version,
                        record.created_at.isoformat(),
                        record.updated_at.isoformat(),
                    ),
                )
                connection.commit()

            return storage_result_ok(
                backend="sqlite",
                collection=record.collection,
                record_id=record.record_id,
                path=str(self.db_path),
                message="Record upserted into SQLite repository.",
            )

        except sqlite3.Error as exc:
            return storage_result_error(
                backend="sqlite",
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
        source: str = "sqlite_repository",
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

    def row_to_record(self, row: sqlite3.Row) -> StorageRecord:
        return StorageRecord(
            collection=row["collection"],
            record_id=row["record_id"],
            payload=json.loads(row["payload_json"]),
            metadata=json.loads(row["metadata_json"]),
            source=row["source"],
            schema_version=row["schema_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get(self, *, collection: str, record_id: str) -> StorageReadResult:
        normalized = normalize_collection_name(collection)

        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM records
                WHERE collection = ? AND record_id = ?
                """,
                (normalized, record_id),
            ).fetchone()

        if row is None:
            return StorageReadResult(
                status="NOT_FOUND",
                backend="sqlite",
                collection=normalized,
                message="Record not found.",
            )

        record = self.row_to_record(row)

        return StorageReadResult(
            status="OK",
            backend="sqlite",
            collection=normalized,
            record=record.model_dump(mode="json"),
            message="Record found.",
        )

    def query(self, query: StorageQuery | dict[str, Any]) -> StorageReadResult:
        parsed = query if isinstance(query, StorageQuery) else StorageQuery.model_validate(query)
        normalized = normalize_collection_name(parsed.collection)

        order = "DESC" if parsed.reverse else "ASC"

        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM records
                WHERE collection = ?
                ORDER BY created_at {order}
                LIMIT ?
                """,
                (normalized, max(0, parsed.limit * 5 if parsed.filters else parsed.limit)),
            ).fetchall()

        records = [self.row_to_record(row) for row in rows]

        if parsed.record_id:
            records = [record for record in records if record.record_id == parsed.record_id]

        if parsed.filters:
            records = [record for record in records if record_matches_filters(record, parsed.filters)]

        limited = records[: max(0, parsed.limit)]

        return StorageReadResult(
            status="OK",
            backend="sqlite",
            collection=normalized,
            records=[record.model_dump(mode="json") for record in limited],
            message=f"{len(limited)} record(s) returned.",
            metadata={
                "total_matched": len(records),
                "limit": parsed.limit,
            },
        )


def build_sqlite_repository(db_path: str | Path | None = None) -> SQLiteRepository:
    return SQLiteRepository(db_path=db_path)