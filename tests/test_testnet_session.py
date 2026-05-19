from ops.testnet_session import (
    TestnetOrderEvent,
    build_testnet_session_metrics,
    build_testnet_session_report,
    export_testnet_session_report,
    load_testnet_events_jsonl,
)


def sample_events():
    return [
        TestnetOrderEvent(
            side="BUY",
            quantity=0.01,
            requested_price=60000,
            executed_price=60001,
            status="FILLED",
            latency_ms=100,
            estimated_slippage_pct=0.0005,
            realized_slippage_pct=0.0004,
            fee_usd=0.05,
            pnl_usd=1,
        ),
        TestnetOrderEvent(
            side="BUY",
            quantity=0.01,
            requested_price=60000,
            status="REJECTED",
            rejection_reason="unit_test",
        ),
    ]


def test_build_testnet_session_metrics():
    metrics = build_testnet_session_metrics(sample_events())

    assert metrics.events_total == 2
    assert metrics.filled_orders == 1
    assert metrics.rejected_orders == 1
    assert metrics.fill_rate == 0.5


def test_build_testnet_session_report():
    report = build_testnet_session_report(
        events=sample_events(),
        session_name="unit_session",
    )

    assert report.session_name == "unit_session"
    assert report.metrics["events_total"] == 2


def test_export_and_load_testnet_session_report(tmp_path):
    report = build_testnet_session_report(
        events=sample_events(),
        session_name="unit_session",
    )

    paths = export_testnet_session_report(
        report,
        output_dir=tmp_path,
        name="unit_session",
    )

    assert paths["summary"].exists()
    assert paths["events"].exists()

    loaded = load_testnet_events_jsonl(paths["events"])

    assert len(loaded) == 2