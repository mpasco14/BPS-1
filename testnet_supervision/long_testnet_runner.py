from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from testnet_readiness.testnet_fill_monitoring import TestnetFillEvent, monitor_testnet_fills_and_rejections
from testnet_readiness.testnet_order_lifecycle import TestnetOrderLifecycleEvent, validate_testnet_order_lifecycle
from testnet_readiness.testnet_portfolio_reconciliation import build_flat_position, reconcile_testnet_portfolio
from testnet_readiness.testnet_reconciliation_engine import run_testnet_reconciliation_engine
from testnet_supervision.credential_readiness import (
    TestnetCredentialReadinessReport,
    evaluate_testnet_credential_readiness,
)
from testnet_supervision.supervised_session_plan import (
    SupervisedTestnetSessionPlan,
    SupervisedTestnetSessionPlanReport,
    build_supervised_testnet_session_plan,
    evaluate_supervised_testnet_session_plan,
)
from testnet_supervision.testnet_evidence_collector import (
    TestnetEvidenceCollectionReport,
    build_demo_testnet_evidence_events,
    collect_testnet_evidence,
)


load_dotenv()

__test__ = False


RunnerStatus = Literal["PASS", "WARN", "FAIL", "STOPPED"]


class LongTestnetRunnerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_supervision")

    simulate: bool = True
    max_loop_iterations: int = 5
    heartbeat_interval_seconds: int = 30
    stop_on_warning: bool = False


class LongTestnetRunnerReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "controlled_long_testnet_runner"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: RunnerStatus
    passed: bool
    simulated: bool

    session_name: str
    started_at: datetime
    ended_at: datetime

    loop_iterations: int
    orders_attempted: int
    orders_submitted: int
    stop_reason: str | None = None

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    credential_readiness: dict[str, Any]
    session_plan: dict[str, Any]
    evidence: dict[str, Any]
    readiness_reports: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_long_testnet_runner_config() -> LongTestnetRunnerConfig:
    return LongTestnetRunnerConfig(
        output_dir=Path(os.getenv("LONG_TESTNET_RUNNER_OUTPUT_DIR", "artifacts/testnet_supervision")),
        simulate=env_bool("LONG_TESTNET_RUNNER_SIMULATE", True),
        max_loop_iterations=env_int("LONG_TESTNET_RUNNER_MAX_LOOP_ITERATIONS", 5),
        heartbeat_interval_seconds=env_int("LONG_TESTNET_RUNNER_HEARTBEAT_INTERVAL_SECONDS", 30),
        stop_on_warning=env_bool("LONG_TESTNET_RUNNER_STOP_ON_WARNING", False),
    )


def build_lifecycle_events_from_evidence(session_name: str = "runner") -> list[TestnetOrderLifecycleEvent]:
    return [
        TestnetOrderLifecycleEvent(event_id="life_1", order_id=f"{session_name}_order_1", event_type="PLANNED", requested_qty=0.001, price=60000),
        TestnetOrderLifecycleEvent(event_id="life_2", order_id=f"{session_name}_order_1", event_type="SUBMITTED", requested_qty=0.001, price=60000),
        TestnetOrderLifecycleEvent(event_id="life_3", order_id=f"{session_name}_order_1", event_type="ACKNOWLEDGED", requested_qty=0.001, price=60000),
        TestnetOrderLifecycleEvent(event_id="life_4", order_id=f"{session_name}_order_1", event_type="PARTIALLY_FILLED", requested_qty=0.001, filled_qty=0.0005, price=60002),
        TestnetOrderLifecycleEvent(event_id="life_5", order_id=f"{session_name}_order_1", event_type="FILLED", requested_qty=0.001, filled_qty=0.001, price=60003),
    ]


def build_fill_events_from_evidence(session_name: str = "runner") -> list[TestnetFillEvent]:
    return [
        TestnetFillEvent(
            event_id="runner_fill_partial",
            order_id=f"{session_name}_order_1",
            event_type="PARTIAL_FILL",
            expected_price=60000,
            fill_price=60002,
            requested_qty=0.001,
            filled_qty=0.0005,
        ),
        TestnetFillEvent(
            event_id="runner_fill_final",
            order_id=f"{session_name}_order_1",
            event_type="FILL",
            expected_price=60000,
            fill_price=60003,
            requested_qty=0.001,
            filled_qty=0.0005,
        ),
    ]


def run_controlled_long_testnet_session(
    *,
    plan: SupervisedTestnetSessionPlan | dict[str, Any] | None = None,
    credential_readiness: TestnetCredentialReadinessReport | dict[str, Any] | None = None,
    config: LongTestnetRunnerConfig | None = None,
    metadata: dict[str, Any] | None = None,
) -> LongTestnetRunnerReport:
    resolved_config = config or load_long_testnet_runner_config()

    credentials = (
        credential_readiness
        if isinstance(credential_readiness, TestnetCredentialReadinessReport)
        else TestnetCredentialReadinessReport.model_validate(credential_readiness)
        if credential_readiness is not None
        else evaluate_testnet_credential_readiness()
    )

    resolved_plan = (
        plan
        if isinstance(plan, SupervisedTestnetSessionPlan)
        else SupervisedTestnetSessionPlan.model_validate(plan)
        if plan is not None
        else build_supervised_testnet_session_plan()
    )

    plan_report = evaluate_supervised_testnet_session_plan(
        plan=resolved_plan,
        credential_readiness=credentials,
    )

    started_at = datetime.now(timezone.utc)
    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    stop_reason: str | None = None

    if not credentials.passed:
        blockers.append("credential_readiness_not_passed")

    if not plan_report.passed:
        blockers.append("supervised_session_plan_not_passed")
        blockers.extend([f"plan:{item}" for item in plan_report.blockers])

    warnings.extend([f"credential:{item}" for item in credentials.warnings])
    warnings.extend([f"plan:{item}" for item in plan_report.warnings])

    loop_iterations = 0
    orders_attempted = 0
    orders_submitted = 0

    if blockers:
        stop_reason = "preflight_blocked"
        evidence_report = collect_testnet_evidence(events=[])
    else:
        loop_iterations = min(resolved_config.max_loop_iterations, max(1, resolved_plan.max_orders))
        orders_attempted = 1

        if resolved_config.simulate:
            orders_submitted = 1
            evidence_events = build_demo_testnet_evidence_events(session_name=resolved_plan.session_name)
            evidence_report = collect_testnet_evidence(events=evidence_events)
        else:
            if not resolved_plan.allow_testnet_order_submission:
                blockers.append("real_runner_requires_testnet_order_submission_allowed")
                stop_reason = "order_submission_not_allowed"
                evidence_report = collect_testnet_evidence(events=[])
            else:
                warnings.append("non_simulated_runner_placeholder")
                recommendations.append("Conectar aqui o cliente Binance testnet real para envio e coleta.")
                evidence_events = build_demo_testnet_evidence_events(session_name=resolved_plan.session_name)
                evidence_report = collect_testnet_evidence(events=evidence_events)
                orders_submitted = 1

    if evidence_report.warnings:
        warnings.extend([f"evidence:{item}" for item in evidence_report.warnings])

    if not evidence_report.passed:
        blockers.append("evidence_collection_not_passed")
        blockers.extend([f"evidence:{item}" for item in evidence_report.blockers])

    lifecycle = validate_testnet_order_lifecycle(
        events=build_lifecycle_events_from_evidence(resolved_plan.session_name)
    )
    fill_monitor = monitor_testnet_fills_and_rejections(
        events=build_fill_events_from_evidence(resolved_plan.session_name)
    )
    portfolio = reconcile_testnet_portfolio(
        local_position=build_flat_position(resolved_plan.symbol),
        exchange_position=build_flat_position(resolved_plan.symbol),
    )
    recon_engine = run_testnet_reconciliation_engine(
        lifecycle=lifecycle,
        fill_monitor=fill_monitor,
        portfolio_reconciliation=portfolio,
    )

    if not recon_engine.passed:
        blockers.append("testnet_reconciliation_engine_not_passed")
        blockers.extend([f"recon:{item}" for item in recon_engine.blockers])

    warnings.extend([f"recon:{item}" for item in recon_engine.warnings])

    if resolved_config.stop_on_warning and warnings:
        blockers.append("runner_stop_on_warning_enabled")
        stop_reason = "warning_detected"

    passed = not blockers
    ended_at = datetime.now(timezone.utc)

    if stop_reason is None:
        stop_reason = "completed" if passed else "blocked"

    recommendations.append("Revisar evidências antes de repetir sessão mais longa.")
    recommendations.append("Não promover para micro-live sem múltiplas sessões testnet aprovadas.")

    return LongTestnetRunnerReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        simulated=resolved_config.simulate,
        session_name=resolved_plan.session_name,
        started_at=started_at,
        ended_at=ended_at,
        loop_iterations=loop_iterations,
        orders_attempted=orders_attempted,
        orders_submitted=orders_submitted,
        stop_reason=stop_reason,
        blockers=blockers,
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        credential_readiness=credentials.model_dump(mode="json"),
        session_plan=plan_report.model_dump(mode="json"),
        evidence=evidence_report.model_dump(mode="json"),
        readiness_reports={
            "lifecycle": lifecycle.model_dump(mode="json"),
            "fill_monitor": fill_monitor.model_dump(mode="json"),
            "portfolio_reconciliation": portfolio.model_dump(mode="json"),
            "reconciliation_engine": recon_engine.model_dump(mode="json"),
        },
        config={
            **resolved_config.model_dump(mode="json"),
            "metadata": metadata or {},
        },
    )


def export_long_testnet_runner_report(
    report: LongTestnetRunnerReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "long_testnet_runner_report",
) -> Path:
    config = load_long_testnet_runner_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path