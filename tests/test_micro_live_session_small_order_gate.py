from micro_live_session.dry_run_signal import MicroLiveDryRunSignalInput, evaluate_micro_live_dry_run_signal
from micro_live_session.read_only_check import FirstMicroLiveReadOnlyCheckReport
from micro_live_session.session_models import MicroLiveSessionConfig
from micro_live_session.small_order_gate import build_micro_live_small_order_gate


def passing_read_only():
    return FirstMicroLiveReadOnlyCheckReport(
        status="PASS",
        passed=True,
        prep_gate_passed=True,
        prep_gate_decision="APPROVED_FOR_MICRO_LIVE_SESSION",
        live_order_allowed=False,
        dry_run=True,
        go_no_go_report={},
    )


def test_micro_live_small_order_gate_dry_run_passes():
    config = MicroLiveSessionConfig(
        dry_run=True,
        allow_live_order=False,
        quantity=0.001,
        price=6000,
        max_notional_usd=10,
    )
    signal = evaluate_micro_live_dry_run_signal(
        signal_input=MicroLiveDryRunSignalInput(confidence=0.8, edge_pct=0.003),
        config=config,
    )

    report = build_micro_live_small_order_gate(
        read_only_check=passing_read_only(),
        dry_run_signal=signal,
        config=config,
    )

    assert report.passed is True
    assert report.status == "DRY_RUN"
    assert report.submitted is False


def test_micro_live_small_order_gate_blocks_large_notional():
    config = MicroLiveSessionConfig(
        dry_run=True,
        quantity=0.001,
        price=60000,
        max_notional_usd=10,
    )
    signal = evaluate_micro_live_dry_run_signal(
        signal_input=MicroLiveDryRunSignalInput(confidence=0.8, edge_pct=0.003),
        config=config,
    )

    report = build_micro_live_small_order_gate(
        read_only_check=passing_read_only(),
        dry_run_signal=signal,
        config=config,
    )

    assert report.passed is False
    assert "order_notional_above_micro_live_limit" in report.blockers