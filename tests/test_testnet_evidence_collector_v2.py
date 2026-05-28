from testnet_supervision.testnet_evidence_collector import (
    TestnetEvidenceEvent,
    build_demo_testnet_evidence_events,
    collect_testnet_evidence,
)


def test_testnet_evidence_collector_demo_passes():
    report = collect_testnet_evidence(
        events=build_demo_testnet_evidence_events(session_name="unit_evidence")
    )

    assert report.passed is True
    assert report.fill_rate == 1.0
    assert report.final_flat is True


def test_testnet_evidence_collector_blocks_missing_final_flat():
    events = [
        TestnetEvidenceEvent(event_id="start", event_type="SESSION_STARTED", session_name="unit"),
        TestnetEvidenceEvent(event_id="submitted", event_type="ORDER_SUBMITTED", session_name="unit", order_id="o1", requested_qty=0.001),
        TestnetEvidenceEvent(event_id="ack", event_type="ORDER_ACK", session_name="unit", order_id="o1", requested_qty=0.001),
        TestnetEvidenceEvent(event_id="fill", event_type="ORDER_FILL", session_name="unit", order_id="o1", requested_qty=0.001, filled_qty=0.001),
    ]

    report = collect_testnet_evidence(events=events)

    assert report.passed is False
    assert "final_position_not_flat" in report.blockers

    def test_testnet_evidence_export_accepts_dict(tmp_path):
    report = collect_testnet_evidence(
        events=build_demo_testnet_evidence_events(session_name="unit_export_dict")
    )

    path = export_testnet_evidence_collection_report(
        report.model_dump(mode="json"),
        output_dir=tmp_path,
        name="evidence_from_dict",
    )

    assert path.exists()