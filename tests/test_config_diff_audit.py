from config_management.config_diff_audit import (
    ConfigAuditRecord,
    append_config_audit_record,
    build_config_diff_report,
    load_config_audit_records,
)


def test_config_diff_detects_changes():
    report = build_config_diff_report(
        before={"strategy": {"profile": "conservative", "risk": 0.2}},
        after={"strategy": {"profile": "balanced", "risk": 0.2, "edge": 0.01}},
    )

    assert report.changes_count == 2
    assert report.changed_count == 1
    assert report.added_count == 1


def test_config_audit_append_and_load(tmp_path):
    path = tmp_path / "audit.jsonl"

    report = build_config_diff_report(
        before={"a": 1},
        after={"a": 2},
    )

    append_config_audit_record(
        ConfigAuditRecord(
            actor="unit",
            reason="unit test",
            diff=report.model_dump(mode="json"),
        ),
        path=path,
    )

    records = load_config_audit_records(path)

    assert len(records) == 1
    assert records[0].actor == "unit"