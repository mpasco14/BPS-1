from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from testnet_supervision.credential_readiness import TestnetCredentialReadinessReport
from testnet_supervision.long_testnet_runner import LongTestnetRunnerReport
from testnet_supervision.supervised_session_plan import SupervisedTestnetSessionPlanReport
from testnet_supervision.testnet_evidence_collector import TestnetEvidenceCollectionReport


load_dotenv()

__test__ = False


PromotionDecision = Literal[
    "REPEAT_TESTNET",
    "FIX_REQUIRED",
    "APPROVED_FOR_LONGER_TESTNET",
    "APPROVED_FOR_MICRO_LIVE_PREP",
    "BLOCKED",
]

ReviewStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetSessionReviewConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_supervision")

    require_credentials_pass: bool = True
    require_plan_pass: bool = True
    require_runner_pass: bool = True
    require_evidence_pass: bool = True

    min_duration_for_promotion_minutes: int = 30


class TestnetSessionReviewGateReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_session_review_promotion_gate"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ReviewStatus
    passed: bool
    decision: PromotionDecision

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    credential_readiness: dict[str, Any]
    session_plan: dict[str, Any]
    runner: dict[str, Any]
    evidence: dict[str, Any]
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


def load_testnet_session_review_config() -> TestnetSessionReviewConfig:
    return TestnetSessionReviewConfig(
        output_dir=Path(os.getenv("TESTNET_SESSION_REVIEW_OUTPUT_DIR", "artifacts/testnet_supervision")),
        require_credentials_pass=env_bool("TESTNET_SESSION_REVIEW_REQUIRE_CREDENTIALS_PASS", True),
        require_plan_pass=env_bool("TESTNET_SESSION_REVIEW_REQUIRE_PLAN_PASS", True),
        require_runner_pass=env_bool("TESTNET_SESSION_REVIEW_REQUIRE_RUNNER_PASS", True),
        require_evidence_pass=env_bool("TESTNET_SESSION_REVIEW_REQUIRE_EVIDENCE_PASS", True),
        min_duration_for_promotion_minutes=env_int("TESTNET_SESSION_REVIEW_MIN_DURATION_FOR_PROMOTION_MINUTES", 30),
    )


def review_testnet_session_for_promotion(
    *,
    credential_readiness: TestnetCredentialReadinessReport | dict[str, Any],
    session_plan: SupervisedTestnetSessionPlanReport | dict[str, Any],
    runner: LongTestnetRunnerReport | dict[str, Any],
    evidence: TestnetEvidenceCollectionReport | dict[str, Any],
    config: TestnetSessionReviewConfig | None = None,
) -> TestnetSessionReviewGateReport:
    resolved_config = config or load_testnet_session_review_config()

    credentials = (
        credential_readiness
        if isinstance(credential_readiness, TestnetCredentialReadinessReport)
        else TestnetCredentialReadinessReport.model_validate(credential_readiness)
    )
    plan = (
        session_plan
        if isinstance(session_plan, SupervisedTestnetSessionPlanReport)
        else SupervisedTestnetSessionPlanReport.model_validate(session_plan)
    )
    runner_report = (
        runner
        if isinstance(runner, LongTestnetRunnerReport)
        else LongTestnetRunnerReport.model_validate(runner)
    )
    evidence_report = (
        evidence
        if isinstance(evidence, TestnetEvidenceCollectionReport)
        else TestnetEvidenceCollectionReport.model_validate(evidence)
    )

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved_config.require_credentials_pass and not credentials.passed:
        blockers.append("credential_readiness_not_passed")
        blockers.extend([f"credential:{item}" for item in credentials.blockers])

    if resolved_config.require_plan_pass and not plan.passed:
        blockers.append("session_plan_not_passed")
        blockers.extend([f"plan:{item}" for item in plan.blockers])

    if resolved_config.require_runner_pass and not runner_report.passed:
        blockers.append("runner_not_passed")
        blockers.extend([f"runner:{item}" for item in runner_report.blockers])

    if resolved_config.require_evidence_pass and not evidence_report.passed:
        blockers.append("evidence_not_passed")
        blockers.extend([f"evidence:{item}" for item in evidence_report.blockers])

    warnings.extend([f"credential:{item}" for item in credentials.warnings])
    warnings.extend([f"plan:{item}" for item in plan.warnings])
    warnings.extend([f"runner:{item}" for item in runner_report.warnings])
    warnings.extend([f"evidence:{item}" for item in evidence_report.warnings])

    plan_duration = plan.plan.get("duration_minutes", 0)

    if evidence_report.rejection_count > 0:
        blockers.append("rejections_detected")
        recommendations.append("Investigar rejeições antes de repetir ou aumentar duração.")

    if not evidence_report.final_flat:
        blockers.append("session_did_not_end_flat")
        recommendations.append("Corrigir processo de encerramento e reconciliação.")

    if runner_report.simulated:
        warnings.append("runner_was_simulated")
        recommendations.append("Após simulação, rodar sessão testnet real supervisionada com API de testnet.")

    if blockers:
        decision: PromotionDecision = "FIX_REQUIRED"
    elif plan_duration >= resolved_config.min_duration_for_promotion_minutes and not evidence_report.rejection_count:
        decision = "APPROVED_FOR_LONGER_TESTNET"
    else:
        decision = "REPEAT_TESTNET"

    if decision == "APPROVED_FOR_LONGER_TESTNET":
        recommendations.append("Próximo passo recomendado: sessão testnet supervisionada de 2 horas.")

    if decision == "APPROVED_FOR_MICRO_LIVE_PREP":
        recommendations.append("Micro-live prep exige aprovação humana e nova fase específica.")

    passed = not blockers

    return TestnetSessionReviewGateReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        decision=decision,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        credential_readiness=credentials.model_dump(mode="json"),
        session_plan=plan.model_dump(mode="json"),
        runner=runner_report.model_dump(mode="json"),
        evidence=evidence_report.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_testnet_session_review_gate_report(
    report: TestnetSessionReviewGateReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_session_review_gate_report",
) -> Path:
    config = load_testnet_session_review_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path