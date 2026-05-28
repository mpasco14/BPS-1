from data_persistence.storage_abstraction import (
    create_storage_record,
    normalize_collection_name,
    record_matches_filters,
    stable_payload_hash,
)


def test_normalize_collection_name():
    assert normalize_collection_name("System Events") == "system_events"
    assert normalize_collection_name("risk/events") == "risk_events"


def test_create_storage_record_stable_id():
    payload = {"x": 1}
    record_a = create_storage_record(collection="events", payload=payload, stable_id=True)
    record_b = create_storage_record(collection="events", payload=payload, stable_id=True)

    assert record_a.record_id == record_b.record_id
    assert stable_payload_hash(payload)


def test_record_matches_filters():
    record = create_storage_record(
        collection="events",
        payload={"status": "OK"},
        metadata={"env": "test"},
    )

    assert record_matches_filters(record, {"payload.status": "OK"}) is True
    assert record_matches_filters(record, {"metadata.env": "test"}) is True
    assert record_matches_filters(record, {"payload.status": "FAIL"}) is False