from data_persistence.sqlite_repository import SQLiteRepository
from data_persistence.storage_abstraction import StorageQuery


def test_sqlite_repository_create_and_get(tmp_path):
    repo = SQLiteRepository(db_path=tmp_path / "storage.db")

    write = repo.create(
        collection="events",
        record_id="event_1",
        payload={"status": "OK"},
    )

    read = repo.get(collection="events", record_id="event_1")

    assert write.status == "OK"
    assert read.status == "OK"
    assert read.record["payload"]["status"] == "OK"


def test_sqlite_repository_query_filters(tmp_path):
    repo = SQLiteRepository(db_path=tmp_path / "storage.db")

    repo.create(collection="events", record_id="a", payload={"status": "OK"})
    repo.create(collection="events", record_id="b", payload={"status": "FAIL"})

    result = repo.query(
        StorageQuery(
            collection="events",
            filters={"payload.status": "OK"},
        )
    )

    assert result.status == "OK"
    assert len(result.records) == 1
    assert result.records[0]["record_id"] == "a"