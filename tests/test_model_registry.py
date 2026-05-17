from models.model_registry import (
    ModelRegistryRecord,
    load_latest_record,
    load_registry_record,
    register_model,
    save_registry_record,
    sha256_json,
)


def test_sha256_json_is_stable():
    assert sha256_json({"a": 1}) == sha256_json({"a": 1})


def test_save_and_load_registry_record(tmp_path):
    record = ModelRegistryRecord(
        model_name="test_model",
        model_version="v1",
        model_type="baseline",
        feature_columns=["a", "b"],
    )

    path = save_registry_record(record, base_dir=tmp_path)
    loaded = load_registry_record(path)

    assert loaded.model_name == "test_model"
    assert loaded.model_version == "v1"


def test_register_model_and_load_latest(tmp_path):
    record = register_model(
        model_name="test_model",
        model_version="v1",
        model_type="baseline",
        feature_columns=["a", "b"],
        metrics={"log_loss": 0.5},
        dataset_payload=[{"a": 1}],
        base_dir=tmp_path,
    )

    latest = load_latest_record("test_model", base_dir=tmp_path)

    assert latest.model_name == record.model_name
    assert latest.dataset_hash is not None
    assert latest.metrics["log_loss"] == 0.5