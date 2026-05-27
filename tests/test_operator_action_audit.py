from live_ops.operator_action_audit import (
    OperatorActionRecord,
    append_operator_action_record,
    build_operator_action_audit_report,
    load_operator_action_records,
)


def test_operator_action_audit_hash_chain(tmp_path):
    path = tmp_path / "actions.jsonl"

    append_operator_action_record(
        OperatorActionRecord(
            action_id="a1",
            command="STATUS",
            status="EXECUTED",
            reason="unit",
        ),
        path=path,
    )

    append_operator_action_record(
        OperatorActionRecord(
            action_id="a2",
            command="ENTER_SAFE_MODE",
            status="EXECUTED",
            reason="unit",
        ),
        path=path,
    )

    records = load_operator_action_records(path)
    report = build_operator_action_audit_report(records=records)

    assert len(records) == 2
    assert report.valid_hash_chain is True
    assert records[1].previous_hash == records[0].action_hash