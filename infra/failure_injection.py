from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


FailureType = Literal[
    "REDIS_DOWN",
    "KAFKA_DOWN",
    "BINANCE_REST_429",
    "BINANCE_WS_DISCONNECT",
    "MODEL_NAN",
    "STATE_FILE_MISSING",
    "ORDER_SUBMISSION_ERROR",
    "UNKNOWN",
]

ChaosStatus = Literal["PASS", "WARN", "FAIL"]


class FailureInjectionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/infra")
    require_safe_actions: bool = True


class FailureScenario(BaseModel):
    model_config = ConfigDict(extra="allow")

    scenario_id: str
    failure_type: FailureType
    description: str = ""

    observed_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailureScenarioResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    scenario_id: str
    failure_type: FailureType

    status: ChaosStatus
    passed: bool

    expected_actions: list[str] = Field(default_factory=list)
    observed_actions: list[str] = Field(default_factory=list)
    missing_actions: list[str] = Field(default_factory=list)
    unsafe_actions: list[str] = Field(default_factory=list)

    message: str


class FailureInjectionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "failure_injection"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: ChaosStatus

    scenarios_count: int
    pass_count: int
    warn_count: int
    fail_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    results: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


EXPECTED_ACTIONS: dict[str, list[str]] = {
    "REDIS_DOWN": ["use_local_fallback", "do_not_open_new_large_positions", "emit_alert"],
    "KAFKA_DOWN": ["persist_events_locally", "emit_alert"],
    "BINANCE_REST_429": ["retry_with_backoff", "do_not_spam_api", "emit_alert"],
    "BINANCE_WS_DISCONNECT": ["activate_kill_switch_if_timeout", "block_new_orders", "emit_alert"],
    "MODEL_NAN": ["block_signal", "mark_model_invalid", "emit_alert"],
    "STATE_FILE_MISSING": ["initialize_state_snapshot", "block_new_orders_until_initialized"],
    "ORDER_SUBMISSION_ERROR": ["mark_order_failed", "do_not_retry_without_policy", "emit_alert"],
    "UNKNOWN": ["safe_mode", "emit_alert"],
}

UNSAFE_ACTIONS = {
    "submit_live_order",
    "increase_capital",
    "disable_kill_switch",
    "ignore_failure",
    "retry_forever",
    "continue_without_state",
}


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_failure_injection_config() -> FailureInjectionConfig:
    return FailureInjectionConfig(
        output_dir=Path(os.getenv("FAILURE_INJECTION_OUTPUT_DIR", "artifacts/infra")),
        require_safe_actions=env_bool("FAILURE_INJECTION_REQUIRE_SAFE_ACTIONS", True),
    )


def evaluate_failure_scenario(
    scenario: FailureScenario | dict[str, Any],
    *,
    config: FailureInjectionConfig | None = None,
) -> FailureScenarioResult:
    resolved_config = config or load_failure_injection_config()
    resolved = scenario if isinstance(scenario, FailureScenario) else FailureScenario.model_validate(scenario)

    expected = EXPECTED_ACTIONS.get(resolved.failure_type, EXPECTED_ACTIONS["UNKNOWN"])
    observed = list(resolved.observed_actions)

    missing = [action for action in expected if action not in observed]
    unsafe = [action for action in observed if action in UNSAFE_ACTIONS]

    if unsafe:
        return FailureScenarioResult(
            scenario_id=resolved.scenario_id,
            failure_type=resolved.failure_type,
            status="FAIL",
            passed=False,
            expected_actions=expected,
            observed_actions=observed,
            missing_actions=missing,
            unsafe_actions=unsafe,
            message="Cenário executou ação insegura.",
        )

    if resolved_config.require_safe_actions and missing:
        return FailureScenarioResult(
            scenario_id=resolved.scenario_id,
            failure_type=resolved.failure_type,
            status="FAIL",
            passed=False,
            expected_actions=expected,
            observed_actions=observed,
            missing_actions=missing,
            unsafe_actions=unsafe,
            message="Cenário não executou todas as ações seguras esperadas.",
        )

    if missing:
        return FailureScenarioResult(
            scenario_id=resolved.scenario_id,
            failure_type=resolved.failure_type,
            status="WARN",
            passed=True,
            expected_actions=expected,
            observed_actions=observed,
            missing_actions=missing,
            unsafe_actions=unsafe,
            message="Cenário passou, mas faltam ações recomendadas.",
        )

    return FailureScenarioResult(
        scenario_id=resolved.scenario_id,
        failure_type=resolved.failure_type,
        status="PASS",
        passed=True,
        expected_actions=expected,
        observed_actions=observed,
        missing_actions=[],
        unsafe_actions=[],
        message="Cenário respondeu de forma segura.",
    )


def build_failure_injection_report(
    *,
    scenarios: list[FailureScenario | dict[str, Any]],
    config: FailureInjectionConfig | None = None,
) -> FailureInjectionReport:
    resolved_config = config or load_failure_injection_config()
    results = [
        evaluate_failure_scenario(scenario, config=resolved_config)
        for scenario in scenarios
    ]

    pass_count = sum(1 for item in results if item.status == "PASS")
    warn_count = sum(1 for item in results if item.status == "WARN")
    fail_count = sum(1 for item in results if item.status == "FAIL")

    blockers = [item.scenario_id for item in results if item.status == "FAIL"]
    warnings = [item.scenario_id for item in results if item.status == "WARN"]

    passed = not blockers

    return FailureInjectionReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        scenarios_count=len(results),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blockers=blockers,
        warnings=warnings,
        results=[item.model_dump(mode="json") for item in results],
        config=resolved_config.model_dump(mode="json"),
    )


def demo_failure_scenarios() -> list[FailureScenario]:
    return [
        FailureScenario(
            scenario_id="redis_down_demo",
            failure_type="REDIS_DOWN",
            observed_actions=["use_local_fallback", "do_not_open_new_large_positions", "emit_alert"],
        ),
        FailureScenario(
            scenario_id="binance_429_demo",
            failure_type="BINANCE_REST_429",
            observed_actions=["retry_with_backoff", "do_not_spam_api", "emit_alert"],
        ),
        FailureScenario(
            scenario_id="model_nan_demo",
            failure_type="MODEL_NAN",
            observed_actions=["block_signal", "mark_model_invalid", "emit_alert"],
        ),
    ]


def export_failure_injection_report(
    report: FailureInjectionReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "failure_injection_latest",
) -> Path:
    config = load_failure_injection_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path