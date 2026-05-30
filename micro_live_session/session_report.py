from __future__ import annotations

from pathlib import Path

from micro_live.go_no_go_report import MicroLiveGoNoGoReport, run_micro_live_preparation_gate
from micro_live_session.dry_run_signal import MicroLiveDryRunSignalInput, evaluate_micro_live_dry_run_signal
from micro_live_session.fill_reconciliation_review import review_micro_live_fill_reconciliation
from micro_live_session.kill_switch_validation import validate_micro_live_kill_switch
from micro_live_session.read_only_check import build_first_micro_live_read_only_check
from micro_live_session.session_models import (
    MicroLiveSessionConfig,
    MicroLiveSessionReport,
    export_micro_live_session_json,
    load_micro_live_session_config,
)
from micro_live_session.small_order_gate import build_micro_live_small_order_gate


def build_micro_live_session_report(
    *,
    config: MicroLiveSessionConfig | None = None,
    go_no_go_report: MicroLiveGoNoGoReport | dict | None = None,
    signal_input: MicroLiveDryRunSignalInput | dict | None = None,
) -> MicroLiveSessionReport:
    resolved = config or load_micro_live_session_config()

    gate = (
        go_no_go_report
        if isinstance(go_no_go_report, MicroLiveGoNoGoReport)
        else MicroLiveGoNoGoReport.model_validate(go_no_go_report)
        if go_no_go_report is not None
        else run_micro_live_preparation_gate()
    )

    read_only = build_first_micro_live_read_only_check(
        go_no_go_report=gate,
        config=resolved,
    )

    signal = evaluate_micro_live_dry_run_signal(
        signal_input=signal_input,
        config=resolved,
    )

    order = build_micro_live_small_order_gate(
        read_only_check=read_only,
        dry_run_signal=signal,
        config=resolved,
    )

    fill_recon = review_micro_live_fill_reconciliation(
        small_order=order,
        submitted=order.submitted,
        filled=False,
        canceled=False,
        rejected=False,
        local_position_qty=0.0,
        exchange_position_qty=0.0,
        config=resolved,
    )

    kill_switch = validate_micro_live_kill_switch(config=resolved)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    components = {
        "read_only": read_only,
        "dry_run_signal": signal,
        "small_order": order,
        "fill_reconciliation": fill_recon,
        "kill_switch": kill_switch,
    }

    for name, report in components.items():
        if not report.passed:
            blockers.append(f"{name}_not_passed")
            blockers.extend([f"{name}:{item}" for item in report.blockers])
        warnings.extend([f"{name}:{item}" for item in report.warnings])
        recommendations.extend(report.recommendations)

    if resolved.dry_run:
        decision = "DRY_RUN_ONLY"
    elif blockers:
        decision = "BLOCKED"
    elif resolved.allow_live_order:
        decision = "APPROVED_FOR_ONE_MICRO_LIVE_ORDER"
    else:
        decision = "BLOCKED"
        blockers.append("live_order_not_allowed")

    if blockers:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    passed = not blockers

    recommendations.append("Esta sessão permite no máximo uma ordem micro-live se aprovada.")
    recommendations.append("Nova sessão exige novo relatório e nova aprovação humana.")

    return MicroLiveSessionReport(
        status=status,
        passed=passed,
        decision=decision,
        session_name=resolved.session_name,
        dry_run=resolved.dry_run,
        live_order_allowed=resolved.allow_live_order,
        read_only_passed=read_only.passed,
        dry_run_signal_passed=signal.passed,
        order_gate_passed=order.passed,
        fill_reconciliation_passed=fill_recon.passed,
        kill_switch_passed=kill_switch.passed,
        submitted=order.submitted,
        filled=fill_recon.filled,
        canceled=fill_recon.canceled,
        final_flat=fill_recon.final_flat,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        read_only_check=read_only.model_dump(mode="json"),
        dry_run_signal=signal.model_dump(mode="json"),
        small_order=order.model_dump(mode="json"),
        fill_reconciliation=fill_recon.model_dump(mode="json"),
        kill_switch=kill_switch.model_dump(mode="json"),
        config=resolved.model_dump(mode="json"),
    )


def export_micro_live_session_report(
    report: MicroLiveSessionReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "micro_live_session_report",
) -> Path:
    return export_micro_live_session_json(report, output_dir=output_dir, name=name)