from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from e2e.e2e_failure_scenario import run_e2e_failure_scenario
from e2e.e2e_kill_switch_scenario import run_e2e_kill_switch_scenario
from e2e.e2e_models import (
    E2EFullSystemReport,
    E2EScenarioReport,
    export_e2e_full_system_report,
    export_e2e_scenario_report,
)
from e2e.e2e_paper_trading import run_e2e_paper_trading_scenario
from e2e.e2e_testnet_dry_run import run_e2e_testnet_dry_run_scenario


def build_e2e_full_system_report(
    *,
    scenarios: list[E2EScenarioReport | dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> E2EFullSystemReport:
    parsed = [
        item if isinstance(item, E2EScenarioReport) else E2EScenarioReport.model_validate(item)
        for item in scenarios
    ]

    pass_count = sum(1 for item in parsed if item.status == "PASS")
    warn_count = sum(1 for item in parsed if item.status == "WARN")
    fail_count = sum(1 for item in parsed if item.status == "FAIL")
    expected_blocked_count = sum(1 for item in parsed if item.status == "EXPECTED_BLOCKED")

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    for scenario in parsed:
        if not scenario.passed:
            blockers.append(f"{scenario.scenario_name}:scenario_failed")

        blockers.extend([f"{scenario.scenario_name}:{item}" for item in scenario.blockers if scenario.status == "FAIL"])
        warnings.extend([f"{scenario.scenario_name}:{item}" for item in scenario.warnings])
        recommendations.extend(scenario.recommendations)

    passed = all(item.passed for item in parsed)

    if not parsed:
        passed = False
        blockers.append("no_e2e_scenarios_executed")

    if passed and warn_count == 0:
        status = "PASS"
    elif passed:
        status = "WARN"
    else:
        status = "FAIL"

    return E2EFullSystemReport(
        status=status,
        passed=passed,
        scenarios_count=len(parsed),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        expected_blocked_count=expected_blocked_count,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        scenarios=[item.model_dump(mode="json") for item in parsed],
        metadata=metadata or {},
    )


def run_all_e2e_scenarios(
    *,
    session_name: str = "e2e_full_system",
    export: bool = False,
    output_dir: str | Path | None = None,
) -> E2EFullSystemReport:
    scenarios = [
        run_e2e_paper_trading_scenario(session_name=f"{session_name}_paper"),
        run_e2e_testnet_dry_run_scenario(session_name=f"{session_name}_testnet"),
        run_e2e_failure_scenario(session_name=f"{session_name}_failure", failure_mode="low_confidence_signal"),
        run_e2e_kill_switch_scenario(session_name=f"{session_name}_kill_switch"),
    ]

    report = build_e2e_full_system_report(
        scenarios=scenarios,
        metadata={"session_name": session_name},
    )

    if export:
        path = Path(output_dir or os.getenv("E2E_FULL_REPORT_OUTPUT_DIR", "artifacts/e2e"))
        path.mkdir(parents=True, exist_ok=True)

        for scenario in scenarios:
            export_e2e_scenario_report(
                scenario,
                output_dir=path,
                name=scenario.scenario_name,
            )

        export_e2e_full_system_report(
            report,
            path=path / "e2e_full_system_report.json",
        )

    return report