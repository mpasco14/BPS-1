from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


DeploymentStage = Literal["dev", "paper", "testnet", "micro_live", "live_warmup"]
PromotionAction = Literal["PROMOTE", "HOLD", "BLOCK"]


class DeploymentPromotionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/release")

    require_release_candidate: bool = True
    require_human_approval_for_live: bool = True
    require_production_guard_for_live: bool = True


class DeploymentPromotionInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    release_version: str
    current_stage: DeploymentStage = "dev"
    target_stage: DeploymentStage = "paper"

    release_candidate_passed: bool = False
    quality_gate_passed: bool = False
    security_passed: bool = False
    infra_passed: bool = False

    paper_validated: bool = False
    testnet_validated: bool = False
    micro_live_validated: bool = False

    production_guard_passed: bool = False
    emergency_test_passed: bool = False
    human_approval_valid: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)


class DeploymentPromotionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "deployment_promotion"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    release_version: str
    current_stage: DeploymentStage
    target_stage: DeploymentStage

    action: PromotionAction
    approved: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    inputs: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_deployment_promotion_config() -> DeploymentPromotionConfig:
    return DeploymentPromotionConfig(
        output_dir=Path(os.getenv("DEPLOYMENT_PROMOTION_OUTPUT_DIR", "artifacts/release")),
        require_release_candidate=env_bool("DEPLOYMENT_REQUIRE_RELEASE_CANDIDATE", True),
        require_human_approval_for_live=env_bool("DEPLOYMENT_REQUIRE_HUMAN_APPROVAL_FOR_LIVE", True),
        require_production_guard_for_live=env_bool("DEPLOYMENT_REQUIRE_PRODUCTION_GUARD_FOR_LIVE", True),
    )


def stage_rank(stage: DeploymentStage) -> int:
    order = {
        "dev": 0,
        "paper": 1,
        "testnet": 2,
        "micro_live": 3,
        "live_warmup": 4,
    }

    return order[stage]


def evaluate_deployment_promotion(
    *,
    inputs: DeploymentPromotionInputs | dict[str, Any],
    config: DeploymentPromotionConfig | None = None,
) -> DeploymentPromotionReport:
    resolved_config = config or load_deployment_promotion_config()
    resolved_inputs = inputs if isinstance(inputs, DeploymentPromotionInputs) else DeploymentPromotionInputs.model_validate(inputs)

    blockers: list[str] = []
    warnings: list[str] = []
    required_evidence: list[str] = []
    recommendations: list[str] = []

    if stage_rank(resolved_inputs.target_stage) <= stage_rank(resolved_inputs.current_stage):
        blockers.append("target_stage_not_a_forward_promotion")
        recommendations.append("Escolha um target_stage posterior ao current_stage.")

    if resolved_config.require_release_candidate and not resolved_inputs.release_candidate_passed:
        blockers.append("release_candidate_not_passed")
        required_evidence.append("release_candidate_checklist_report")

    if not resolved_inputs.quality_gate_passed:
        blockers.append("quality_gate_not_passed")
        required_evidence.append("quality_gate_report")

    if not resolved_inputs.security_passed:
        blockers.append("security_not_passed")
        required_evidence.append("security_audit_report")

    if not resolved_inputs.infra_passed:
        blockers.append("infra_not_passed")
        required_evidence.append("infra_validation_reports")

    if resolved_inputs.target_stage in {"testnet", "micro_live", "live_warmup"} and not resolved_inputs.paper_validated:
        blockers.append("paper_not_validated")
        required_evidence.append("paper_trading_report")

    if resolved_inputs.target_stage in {"micro_live", "live_warmup"} and not resolved_inputs.testnet_validated:
        blockers.append("testnet_not_validated")
        required_evidence.append("testnet_session_report")

    if resolved_inputs.target_stage == "live_warmup" and not resolved_inputs.micro_live_validated:
        blockers.append("micro_live_not_validated")
        required_evidence.append("micro_live_audit_report")

    if resolved_inputs.target_stage in {"micro_live", "live_warmup"}:
        if resolved_config.require_production_guard_for_live and not resolved_inputs.production_guard_passed:
            blockers.append("production_guard_not_passed")
            required_evidence.append("production_guard_report")

        if not resolved_inputs.emergency_test_passed:
            blockers.append("emergency_test_not_passed")
            required_evidence.append("emergency_stop_report")

        if resolved_config.require_human_approval_for_live and not resolved_inputs.human_approval_valid:
            blockers.append("human_approval_not_valid")
            required_evidence.append("human_approval_record")

    if resolved_inputs.target_stage == "live_warmup":
        warnings.append("capital_increase_must_remain_manual")
        recommendations.append("Mesmo aprovado, não aumentar capital automaticamente.")

    approved = not blockers

    return DeploymentPromotionReport(
        release_version=resolved_inputs.release_version,
        current_stage=resolved_inputs.current_stage,
        target_stage=resolved_inputs.target_stage,
        action="PROMOTE" if approved else "BLOCK",
        approved=approved,
        blockers=blockers,
        warnings=warnings,
        required_evidence=sorted(set(required_evidence)),
        recommendations=recommendations,
        inputs=resolved_inputs.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_deployment_promotion_report(
    report: DeploymentPromotionReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "deployment_promotion_latest",
) -> Path:
    config = load_deployment_promotion_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path