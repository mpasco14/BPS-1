from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from scenario_testing.chop_sideways_scenario import run_chop_sideways_scenario
from scenario_testing.news_sentiment_shock_scenario import run_news_sentiment_shock_scenario
from scenario_testing.scenario_models import ScenarioTestReport, export_scenario_report
from scenario_testing.trend_regime_scenario import run_trend_regime_scenario
from scenario_testing.volatility_shock_scenario import run_volatility_shock_scenario


class ScenarioTestingFullReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "scenario_testing_full_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: str
    passed: bool

    scenarios_count: int
    pass_count: int
    warn_count: int
    fail_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_scenario_testing_full_report(
    *,
    scenarios: list[ScenarioTestReport | dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> ScenarioTestingFullReport:
    parsed = [
        item if isinstance(item, ScenarioTestReport) else ScenarioTestReport.model_validate(item)
        for item in scenarios
    ]

    pass_count = sum(1 for item in parsed if item.status == "PASS")
    warn_count = sum(1 for item in parsed if item.status == "WARN")
    fail_count = sum(1 for item in parsed if item.status == "FAIL")

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    for scenario in parsed:
        if not scenario.passed:
            blockers.append(f"{scenario.scenario_name}:scenario_failed")

        blockers.extend([f"{scenario.scenario_name}:{item}" for item in scenario.blockers])
        warnings.extend([f"{scenario.scenario_name}:{item}" for item in scenario.warnings])
        recommendations.extend(scenario.recommendations)

    passed = bool(parsed) and all(item.passed for item in parsed)

    if passed and warn_count == 0:
        status = "PASS"
    elif passed:
        status = "WARN"
    else:
        status = "FAIL"

    return ScenarioTestingFullReport(
        status=status,
        passed=passed,
        scenarios_count=len(parsed),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        scenarios=[item.model_dump(mode="json") for item in parsed],
        metadata=metadata or {},
    )


def run_all_scenario_tests(
    *,
    export: bool = False,
    output_dir: str | Path | None = None,
) -> ScenarioTestingFullReport:
    scenarios = [
        run_volatility_shock_scenario(),
        run_trend_regime_scenario(trend_direction="uptrend"),
        run_trend_regime_scenario(trend_direction="downtrend"),
        run_chop_sideways_scenario(),
        run_news_sentiment_shock_scenario(),
    ]

    report = build_scenario_testing_full_report(
        scenarios=scenarios,
        metadata={"suite": "phase_24_scenario_testing"},
    )

    if export:
        path = Path(output_dir or os.getenv("SCENARIO_TESTING_OUTPUT_DIR", "artifacts/scenario_testing"))
        path.mkdir(parents=True, exist_ok=True)

        for scenario in scenarios:
            export_scenario_report(
                scenario,
                output_dir=path,
                name=scenario.scenario_name,
            )

        output_path = path / "scenario_testing_full_report.json"
        output_path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return report