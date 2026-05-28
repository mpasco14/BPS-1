from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ContractStatus = Literal["PASS", "WARN", "FAIL"]


class V1ContractsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/v1_acceptance")

    version: str = "1.0.0"
    release_candidate: str = "rc1"

    target_environments: list[str] = Field(default_factory=lambda: ["paper", "testnet"])

    live_allowed: bool = False
    micro_live_prep_allowed: bool = True

    require_testnet_before_live: bool = True
    require_human_approval_for_live: bool = True
    require_kill_switch: bool = True
    require_reconciliation: bool = True
    require_acceptance_report: bool = True


class V1ScopeContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1.0.0"
    release_candidate: str = "rc1"

    allowed_capabilities: list[str] = Field(default_factory=list)
    forbidden_capabilities: list[str] = Field(default_factory=list)
    target_environments: list[str] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


class V1SafetyContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    live_trading_allowed: bool = False
    micro_live_prep_allowed: bool = True

    require_human_approval_for_live: bool = True
    require_testnet_acceptance_before_live: bool = True
    require_kill_switch: bool = True
    require_safe_mode: bool = True
    require_reconciliation: bool = True
    require_execution_contract: bool = True
    require_no_withdrawal_permissions: bool = True

    metadata: dict[str, Any] = Field(default_factory=dict)


class V1OperatingModesContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    paper_mode_allowed: bool = True
    testnet_mode_allowed: bool = True
    dry_run_required_by_default: bool = True

    live_mode_allowed: bool = False
    micro_live_mode_requires_human_approval: bool = True

    active_active_execution_allowed: bool = False
    active_passive_allowed: bool = True

    primary_executor_required: bool = True
    observer_machine_allowed: bool = True

    metadata: dict[str, Any] = Field(default_factory=dict)


class V1KnownLimitations(BaseModel):
    model_config = ConfigDict(extra="allow")

    limitations: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    future_work: list[str] = Field(default_factory=list)


class V1ContractBundle(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "v1_contract_bundle"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    scope: dict[str, Any]
    safety: dict[str, Any]
    operating_modes: dict[str, Any]
    known_limitations: dict[str, Any]


class V1ContractEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "v1_contract_evaluation"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ContractStatus
    passed: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    contracts: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)

    if not value:
        return default

    return [item.strip() for item in value.split(",") if item.strip()]


def load_v1_contracts_config() -> V1ContractsConfig:
    return V1ContractsConfig(
        output_dir=Path(os.getenv("V1_CONTRACTS_OUTPUT_DIR", "artifacts/v1_acceptance")),
        version=os.getenv("V1_VERSION", "1.0.0"),
        release_candidate=os.getenv("V1_RELEASE_CANDIDATE", "rc1"),
        target_environments=env_list("V1_ENVIRONMENT_TARGET", ["paper", "testnet"]),
        live_allowed=env_bool("V1_LIVE_ALLOWED", False),
        micro_live_prep_allowed=env_bool("V1_MICRO_LIVE_PREP_ALLOWED", True),
        require_testnet_before_live=env_bool("V1_REQUIRE_TESTNET_BEFORE_LIVE", True),
        require_human_approval_for_live=env_bool("V1_REQUIRE_HUMAN_APPROVAL_FOR_LIVE", True),
        require_kill_switch=env_bool("V1_REQUIRE_KILL_SWITCH", True),
        require_reconciliation=env_bool("V1_REQUIRE_RECONCILIATION", True),
        require_acceptance_report=env_bool("V1_REQUIRE_ACCEPTANCE_REPORT", True),
    )


def build_default_v1_contract_bundle(
    *,
    config: V1ContractsConfig | None = None,
) -> V1ContractBundle:
    resolved = config or load_v1_contracts_config()

    scope = V1ScopeContract(
        version=resolved.version,
        release_candidate=resolved.release_candidate,
        target_environments=resolved.target_environments,
        allowed_capabilities=[
            "paper_trading_end_to_end",
            "testnet_dry_run_validation",
            "scenario_testing",
            "risk_gating",
            "sentiment_filtering",
            "portfolio_reconciliation",
            "live_ops_supervision",
            "observability_reports",
            "security_audit_reports",
            "v1_acceptance_reporting",
        ],
        forbidden_capabilities=[
            "automatic_capital_ramp",
            "automatic_leverage_increase",
            "withdrawals",
            "internal_transfers",
            "unapproved_live_order_submission",
            "active_active_order_execution",
            "live_trading_without_human_approval",
        ],
    )

    safety = V1SafetyContract(
        live_trading_allowed=resolved.live_allowed,
        micro_live_prep_allowed=resolved.micro_live_prep_allowed,
        require_human_approval_for_live=resolved.require_human_approval_for_live,
        require_testnet_acceptance_before_live=resolved.require_testnet_before_live,
        require_kill_switch=resolved.require_kill_switch,
        require_reconciliation=resolved.require_reconciliation,
    )

    operating_modes = V1OperatingModesContract(
        paper_mode_allowed=True,
        testnet_mode_allowed=True,
        dry_run_required_by_default=True,
        live_mode_allowed=resolved.live_allowed,
        micro_live_mode_requires_human_approval=True,
        active_active_execution_allowed=False,
        active_passive_allowed=True,
    )

    limitations = V1KnownLimitations(
        limitations=[
            "V1 não promete lucro e não deve ser usada como garantia de performance futura.",
            "V1 prioriza paper/testnet e preparação controlada para micro-live.",
            "V1 ainda não permite active-active com duas máquinas enviando ordens simultaneamente.",
            "V1 exige reconciliação antes de qualquer avanço operacional.",
            "V1 não deve operar live sem aprovação humana explícita.",
        ],
        non_goals=[
            "Distribuição pública como produto final.",
            "Operação live com capital significativo.",
            "Aumento automático de capital.",
            "Saque ou transferência via API.",
        ],
        future_work=[
            "Failover automático com lock distribuído.",
            "Reconciliation live conectada à exchange em tempo real.",
            "Storage compartilhado para múltiplas máquinas.",
            "Relatórios avançados de performance por regime.",
        ],
    )

    return V1ContractBundle(
        scope=scope.model_dump(mode="json"),
        safety=safety.model_dump(mode="json"),
        operating_modes=operating_modes.model_dump(mode="json"),
        known_limitations=limitations.model_dump(mode="json"),
    )


def evaluate_v1_contracts(
    *,
    contracts: V1ContractBundle | dict[str, Any],
    config: V1ContractsConfig | None = None,
) -> V1ContractEvaluationReport:
    resolved = config or load_v1_contracts_config()
    parsed = contracts if isinstance(contracts, V1ContractBundle) else V1ContractBundle.model_validate(contracts)

    scope = V1ScopeContract.model_validate(parsed.scope)
    safety = V1SafetyContract.model_validate(parsed.safety)
    modes = V1OperatingModesContract.model_validate(parsed.operating_modes)
    limitations = V1KnownLimitations.model_validate(parsed.known_limitations)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved.live_allowed and not safety.live_trading_allowed:
        warnings.append("config_live_allowed_but_safety_contract_disallows_live")

    if safety.live_trading_allowed and not safety.require_human_approval_for_live:
        blockers.append("live_requires_human_approval")

    if safety.live_trading_allowed and not safety.require_testnet_acceptance_before_live:
        blockers.append("live_requires_testnet_acceptance")

    if not safety.require_kill_switch:
        blockers.append("kill_switch_required_for_v1")

    if not safety.require_reconciliation:
        blockers.append("reconciliation_required_for_v1")

    if modes.live_mode_allowed and not safety.live_trading_allowed:
        blockers.append("operating_modes_live_conflicts_with_safety_contract")

    if modes.active_active_execution_allowed:
        blockers.append("active_active_execution_forbidden_in_v1")

    if "withdrawals" not in scope.forbidden_capabilities:
        blockers.append("withdrawals_must_be_forbidden")

    if "unapproved_live_order_submission" not in scope.forbidden_capabilities:
        blockers.append("unapproved_live_order_submission_must_be_forbidden")

    if not limitations.limitations:
        warnings.append("known_limitations_missing")

    if resolved.require_acceptance_report:
        recommendations.append("Gerar V1 Acceptance Report antes de qualquer sessão operacional.")

    recommendations.append("Manter V1 em paper/testnet até acceptance completo.")

    passed = not blockers

    return V1ContractEvaluationReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        contracts=parsed.model_dump(mode="json"),
        config=resolved.model_dump(mode="json"),
    )


def export_v1_contract_report(
    report: V1ContractEvaluationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "v1_contracts_report",
) -> Path:
    config = load_v1_contracts_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path