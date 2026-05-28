from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from data_persistence.jsonl_repository import JSONLRepository
from data_persistence.sqlite_repository import SQLiteRepository
from data_persistence.storage_abstraction import StorageQuery


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run storage layer demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/storage/demo")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    jsonl_repo = JSONLRepository(base_dir=output_dir / "jsonl")
    sqlite_repo = SQLiteRepository(db_path=output_dir / "demo_storage.db")

    payload = {
        "event": "storage_demo",
        "status": "OK",
        "phase": "21",
    }

    jsonl_write = jsonl_repo.create(
        collection="system_events",
        payload=payload,
        record_id="storage_demo_jsonl",
        metadata={"backend": "jsonl"},
    )

    sqlite_write = sqlite_repo.create(
        collection="system_events",
        payload=payload,
        record_id="storage_demo_sqlite",
        metadata={"backend": "sqlite"},
    )

    jsonl_query = jsonl_repo.query(StorageQuery(collection="system_events", limit=10))
    sqlite_query = sqlite_repo.query(StorageQuery(collection="system_events", limit=10))

    output = {
        "jsonl_write": jsonl_write.model_dump(mode="json"),
        "sqlite_write": sqlite_write.model_dump(mode="json"),
        "jsonl_query": jsonl_query.model_dump(mode="json"),
        "sqlite_query": sqlite_query.model_dump(mode="json"),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2), flush=True)

    return 0 if jsonl_write.status == "OK" and sqlite_write.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())