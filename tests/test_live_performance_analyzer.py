from ops.live_performance_analyzer import (
    LivePerformanceConfig,
    build_live_performance_report,
    export_live_performance_report,
)
from ops.live_session_recorder import build_demo_live_session_events


def test_live_performance_analyzer_demo_warns_but_passes():
    events = build_demo_live_session_events("unit_perf")

    report = build_live_performance_report(
        events=events,
        session_name="unit_perf",
        config=LivePerformanceConfig(min_trades=5),
    )

    assert report.passed is True
    assert report.filled_count == 1
    assert report.net_pnl_usd == 1.08
    assert "filled_trades_below_minimum" in report.warnings


def test_live_performance_export(tmp_path):
    events = build_demo_live_session_events("unit_perf_export")

    report = build_live_performance_report(
        events=events,
        session_name="unit_perf_export",
    )

    path = export_live_performance_report(
        report,
        output_dir=tmp_path,
        name="unit_perf",
    )

    assert path.exists()