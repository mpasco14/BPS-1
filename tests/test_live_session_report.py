from ops.live_session_report import (
    LiveSessionEvent,
    build_live_session_report,
    export_live_session_report,
)


def test_build_live_session_report():
    report = build_live_session_report(
        session_name="unit",
        dry_run=True,
        events=[
            LiveSessionEvent(
                session_name="unit",
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.01,
                price=60000,
                notional_usd=600,
                margin_usd=20,
                status="PLANNED",
                pnl_usd=1,
                fee_usd=0.05,
            )
        ],
    )

    assert report.events_count == 1
    assert report.net_pnl_usd == 0.95


def test_export_live_session_report(tmp_path):
    report = build_live_session_report(
        session_name="unit",
        dry_run=True,
        events=[],
    )

    path = export_live_session_report(
        report,
        output_dir=tmp_path,
        name="unit_live_report",
    )

    assert path.exists()