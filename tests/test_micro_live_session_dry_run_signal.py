from micro_live_session.dry_run_signal import MicroLiveDryRunSignalInput, evaluate_micro_live_dry_run_signal
from micro_live_session.session_models import MicroLiveSessionConfig


def test_micro_live_dry_run_signal_passes():
    report = evaluate_micro_live_dry_run_signal(
        signal_input=MicroLiveDryRunSignalInput(
            confidence=0.8,
            edge_pct=0.003,
            read_only_passed=True,
            strategy_health_passed=True,
            no_trade_engine_passed=True,
        ),
        config=MicroLiveSessionConfig(min_confidence=0.7, min_edge_pct=0.001),
    )

    assert report.passed is True
    assert report.signal_created is True


def test_micro_live_dry_run_signal_blocks_low_confidence():
    report = evaluate_micro_live_dry_run_signal(
        signal_input=MicroLiveDryRunSignalInput(confidence=0.5, edge_pct=0.003),
        config=MicroLiveSessionConfig(min_confidence=0.7),
    )

    assert report.passed is False
    assert "confidence_below_micro_live_minimum" in report.blockers