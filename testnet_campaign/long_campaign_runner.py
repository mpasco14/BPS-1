from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testnet_campaign.campaign_models import (
    CampaignIterationResult,
    LongTestnetCampaignConfig,
    LongTestnetCampaignReport,
    export_campaign_json,
    load_long_testnet_campaign_config,
)


def _load_iteration_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _build_iteration_command(
    *,
    iteration_name: str,
    config: LongTestnetCampaignConfig,
) -> list[str]:
    command = [
        sys.executable,
        "scripts/run_real_testnet_order_lifecycle.py",
        "--real-testnet",
        "--quantity",
        str(config.quantity),
        "--price",
        str(config.price),
        "--export",
        "--name",
        iteration_name,
    ]

    if config.allow_real_submit:
        command.append("--allow-submit")

    if config.allow_real_cancel:
        command.append("--allow-cancel")

    return command


def run_campaign_iteration(
    *,
    iteration: int,
    config: LongTestnetCampaignConfig,
) -> CampaignIterationResult:
    iteration_name = f"{config.campaign_name}_iteration_{iteration:03d}"
    artifact_path = Path("artifacts/testnet_order_lifecycle") / f"{iteration_name}_report.json"

    command = _build_iteration_command(
        iteration_name=iteration_name,
        config=config,
    )

    started_at = datetime.now(timezone.utc)

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    finished_at = datetime.now(timezone.utc)
    artifact = _load_iteration_artifact(artifact_path)

    blockers = list(artifact.get("blockers", []) or [])
    warnings = list(artifact.get("warnings", []) or [])

    if result.returncode != 0:
        blockers.append("iteration_command_failed")

    passed = bool(artifact.get("passed", False)) and result.returncode == 0

    return CampaignIterationResult(
        iteration=iteration,
        started_at=started_at,
        finished_at=finished_at,
        command=command,
        status=str(artifact.get("status", "FAIL" if result.returncode else "UNKNOWN")),
        passed=passed,
        simulated=bool(artifact.get("simulated", True)),
        submitted=bool(artifact.get("submitted", False)),
        cancel_passed=bool(artifact.get("cancel_passed", False)),
        final_flat=bool(artifact.get("final_flat", False)),
        rejection_detected=bool(artifact.get("rejection_detected", False)),
        fill_detected=bool(artifact.get("fill_detected", False)),
        artifact_path=str(artifact_path),
        return_code=result.returncode,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        metadata={
            "stdout_tail": result.stdout[-2500:],
            "stderr_tail": result.stderr[-2500:],
        },
    )


def build_campaign_report(
    *,
    iterations: list[CampaignIterationResult],
    config: LongTestnetCampaignConfig,
) -> LongTestnetCampaignReport:
    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    iterations_count = len(iterations)
    passed_iterations = sum(1 for item in iterations if item.passed)
    failed_iterations = iterations_count - passed_iterations
    warning_iterations = sum(1 for item in iterations if item.warnings)

    submitted_count = sum(1 for item in iterations if item.submitted)
    cancel_passed_count = sum(1 for item in iterations if item.cancel_passed)
    final_flat_count = sum(1 for item in iterations if item.final_flat)
    rejection_count = sum(1 for item in iterations if item.rejection_detected)
    fill_count = sum(1 for item in iterations if item.fill_detected)

    if iterations_count == 0:
        blockers.append("no_iterations_executed")

    if iterations_count < config.max_iterations:
        blockers.append("campaign_incomplete")

    if failed_iterations > config.max_failed_iterations:
        blockers.append("failed_iterations_above_limit")

    if warning_iterations > config.max_warning_iterations:
        blockers.append("warning_iterations_above_limit")

    if config.require_real_mode and any(item.simulated for item in iterations):
        blockers.append("simulated_iteration_detected")

    if config.require_submit and submitted_count != iterations_count:
        blockers.append("not_all_iterations_submitted")

    if config.require_cancel and cancel_passed_count != iterations_count:
        blockers.append("not_all_iterations_cancel_passed")

    if config.require_final_flat and final_flat_count != iterations_count:
        blockers.append("not_all_iterations_final_flat")

    if config.require_no_rejection and rejection_count > 0:
        blockers.append("rejection_detected")

    for item in iterations:
        for blocker in item.blockers:
            blockers.append(f"iteration_{item.iteration}:{blocker}")

        for warning in item.warnings:
            warnings.append(f"iteration_{item.iteration}:{warning}")

    recommendations.append("Não avançar para 2h antes da sessão 30min passar.")
    recommendations.append("Não avançar para 6h antes da sessão 2h passar.")
    recommendations.append("Não avançar para 12h antes da sessão 6h passar.")
    recommendations.append("Antes de micro-live, revisar todos os artifacts e confirmar ausência de vazamento de credenciais.")

    passed = not blockers

    if passed and warnings:
        status = "WARN"
        decision = "HOLD"
    elif passed:
        status = "PASS"
        decision = "PROMOTE"
    else:
        status = "FAIL"
        decision = "BLOCKED"

    return LongTestnetCampaignReport(
        campaign_name=config.campaign_name,
        symbol=config.symbol,
        status=status,
        passed=passed,
        decision=decision,
        duration_minutes=config.duration_minutes,
        interval_seconds=config.interval_seconds,
        max_iterations=config.max_iterations,
        iterations_count=iterations_count,
        passed_iterations=passed_iterations,
        failed_iterations=failed_iterations,
        warning_iterations=warning_iterations,
        submitted_count=submitted_count,
        cancel_passed_count=cancel_passed_count,
        final_flat_count=final_flat_count,
        rejection_count=rejection_count,
        fill_count=fill_count,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        iterations=iterations,
        config=config.model_dump(mode="json"),
    )


def run_long_testnet_campaign(
    *,
    config: LongTestnetCampaignConfig | None = None,
    sleep_between_iterations: bool = True,
) -> LongTestnetCampaignReport:
    resolved = config or load_long_testnet_campaign_config()
    iterations: list[CampaignIterationResult] = []

    try:
        for index in range(1, resolved.max_iterations + 1):
            print(
                f"[campaign] starting iteration {index}/{resolved.max_iterations} "
                f"name={resolved.campaign_name} symbol={resolved.symbol}",
                flush=True,
            )

            iteration = run_campaign_iteration(
                iteration=index,
                config=resolved,
            )
            iterations.append(iteration)

            print(
                f"[campaign] finished iteration {index}/{resolved.max_iterations} "
                f"passed={iteration.passed} status={iteration.status} "
                f"submitted={iteration.submitted} cancel_passed={iteration.cancel_passed} "
                f"final_flat={iteration.final_flat} blockers={iteration.blockers} warnings={iteration.warnings}",
                flush=True,
            )

            if sleep_between_iterations and index < resolved.max_iterations:
                print(
                    f"[campaign] sleeping {resolved.interval_seconds}s before next iteration",
                    flush=True,
                )
                time.sleep(resolved.interval_seconds)

    except KeyboardInterrupt:
        print(
            "[campaign] interrupted by operator. Building partial BLOCKED report.",
            flush=True,
        )

    return build_campaign_report(
        iterations=iterations,
        config=resolved,
    )

def export_long_testnet_campaign_report(
    report: LongTestnetCampaignReport,
    *,
    output_dir: str | Path | None = None,
    name: str | None = None,
) -> Path:
    return export_campaign_json(
        report,
        output_dir=output_dir,
        name=name or report.campaign_name,
    )