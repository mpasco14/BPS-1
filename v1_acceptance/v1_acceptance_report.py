from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from v1_acceptance.operator_checklist import OperatorChecklistReport
from v1_acceptance.v1_contracts import V1ContractEvaluationReport


load_dotenv()


V1AcceptanceStatus = Literal[
    "V1_ACCEPTED",
    "V1_ACCEPTED_WITH_WARNINGS",
    "V1_BLOCKED",
    "V1_READY_FOR_PAPER_ONLY",
    "V1_READY_FOR_TESTNET",
    "V1_NOT_READY_FOR_LIVE",
]


class V1AcceptanceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/v1_acceptance")
    acceptance_file: Path = Path("artifacts/v1_acceptance/v1_acceptance_report.json")

    require_contracts_pass: bool = True
    require_operator_checklist_pass: bool = True
    require_e2e_pass: bool = True
    require_scenario_testing_pass: bool = True
    require_testnet_acceptance_pass: bool = True
    require_security_pass: bool = True
    require_docs_pass: bool = True
    require_pytest_pass: bool = True


class V1ComponentResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    passed: bool
    status: str = "UNKNOWN"

    required: bool = True
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    evidence_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class V1AcceptanceReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "v1_acceptance_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    version: str = "1.0.0"
    release_candidate: str = "rc1"

    status: V1AcceptanceStatus
    accepted: bool

    paper_ready: bool
    testnet_ready: bool
    live_ready: bool = False

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    components: list[dict[str, Any]] = Field(default_factory=list)

    contracts: dict[str, Any] | None = None
    operator_checklist: dict[str, Any] | None = None

    config: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_v1_acceptance_config() -> V1AcceptanceConfig:
    return V1AcceptanceConfig(
        output_dir=Path(os.getenv("V1_ACCEPTANCE_OUTPUT_DIR", "artifacts/v1_acceptance")),
        acceptance_file=Path(os.getenv("V1_ACCEPTANCE_FILE", "artifacts/v1_acceptance/v1_acceptance_report.json")),
        require_contracts_pass=env_bool("V1_ACCEPTANCE_REQUIRE_CONTRACTS_PASS", True),
        require_operator_checklist_pass=env_bool("V1_ACCEPTANCE_REQUIRE_OPERATOR_CHECKLIST_PASS", True),
        require_e2e_pass=env_bool("V1_ACCEPTANCE_REQUIRE_E2E_PASS", True),
        require_scenario_testing_pass=env_bool("V1_ACCEPTANCE_REQUIRE_SCENARIO_TESTING_PASS", True),
        require_testnet_acceptance_pass=env_bool("V1_ACCEPTANCE_REQUIRE_TESTNET_ACCEPTANCE_PASS", True),
        require_security_pass=env_bool("V1_ACCEPTANCE_REQUIRE_SECURITY_PASS", True),
        require_docs_pass=env_bool("V1_ACCEPTANCE_REQUIRE_DOCS_PASS", True),
        require_pytest_pass=env_bool("V1_ACCEPTANCE_REQUIRE_PYTEST_PASS", True),
    )


def component_from_report(
    *,
    name: str,
    passed: bool,
    status: str,
    required: bool = True,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
    evidence_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> V1ComponentResult:
    return V1ComponentResult(
        name=name,
        passed=passed,
        status=status,
        required=required,
        blockers=blockers or [],
        warnings=warnings or [],
        evidence_path=evidence_path,
        metadata=metadata or {},
    )


def build_v1_acceptance_report(
    *,
    contracts_report: V1ContractEvaluationReport | dict[str, Any],
    operator_checklist_report: OperatorChecklistReport | dict[str, Any],
    components: list[V1ComponentResult | dict[str, Any]],
    version: str | None = None,
    release_candidate: str | None = None,
    config: V1AcceptanceConfig | None = None,
    metadata: dict[str, Any] | None = None,
) -> V1AcceptanceReport:
    resolved = config or load_v1_acceptance_config()

    contracts = contracts_report if isinstance(contracts_report, V1ContractEvaluationReport) else V1ContractEvaluationReport.model_validate(contracts_report)
    checklist = operator_checklist_report if isinstance(operator_checklist_report, OperatorChecklistReport) else OperatorChecklistReport.model_validate(operator_checklist_report)

    parsed_components = [
        item if isinstance(item, V1ComponentResult) else V1ComponentResult.model_validate(item)
        for item in components
    ]

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved.require_contracts_pass and not contracts.passed:
        blockers.append("v1_contracts_not_passed")

    if resolved.require_operator_checklist_pass and not checklist.passed:
        blockers.append("operator_checklist_not_passed")

    warnings.extend([f"contracts:{item}" for item in contracts.warnings])
    warnings.extend([f"operator_checklist:{item}" for item in checklist.warnings])

    recommendations.extend(contracts.recommendations)
    recommendations.extend(checklist.recommendations)

    required_component_names = {
        "e2e": resolved.require_e2e_pass,
        "scenario_testing": resolved.require_scenario_testing_pass,
        "testnet_acceptance": resolved.require_testnet_acceptance_pass,
        "security": resolved.require_security_pass,
        "docs": resolved.require_docs_pass,
        "pytest": resolved.require_pytest_pass,
    }

    by_name = {item.name: item for item in parsed_components}

    for name, required in required_component_names.items():
        component = by_name.get(name)

        if required and component is None:
            blockers.append(f"{name}_component_missing")
            continue

        if required and component is not None and not component.passed:
            blockers.append(f"{name}_component_not_passed")

    for component in parsed_components:
        if component.required and not component.passed:
            blockers.extend([f"{component.name}:{item}" for item in component.blockers])

        warnings.extend([f"{component.name}:{item}" for item in component.warnings])

    e2e_ok = by_name.get("e2e").passed if by_name.get("e2e") else False
    scenario_ok = by_name.get("scenario_testing").passed if by_name.get("scenario_testing") else False
    testnet_ok = by_name.get("testnet_acceptance").passed if by_name.get("testnet_acceptance") else False
    security_ok = by_name.get("security").passed if by_name.get("security") else False
    pytest_ok = by_name.get("pytest").passed if by_name.get("pytest") else False

    paper_ready = contracts.passed and checklist.passed and e2e_ok and pytest_ok
    testnet_ready = paper_ready and scenario_ok and testnet_ok and security_ok

    live_ready = False

    accepted = not blockers

    if not accepted:
        status: V1AcceptanceStatus = "V1_BLOCKED"
    elif testnet_ready and warnings:
        status = "V1_ACCEPTED_WITH_WARNINGS"
    elif testnet_ready:
        status = "V1_ACCEPTED"
    elif paper_ready:
        status = "V1_READY_FOR_PAPER_ONLY"
    else:
        status = "V1_NOT_READY_FOR_LIVE"

    if accepted:
        recommendations.append("V1 aceita estruturalmente para paper/testnet controlado.")
        recommendations.append("Não iniciar live sem fase futura de micro-live approval.")

    return V1AcceptanceReport(
        version=version or os.getenv("V1_VERSION", "1.0.0"),
        release_candidate=release_candidate or os.getenv("V1_RELEASE_CANDIDATE", "rc1"),
        status=status,
        accepted=accepted,
        paper_ready=paper_ready,
        testnet_ready=testnet_ready,
        live_ready=live_ready,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        components=[item.model_dump(mode="json") for item in parsed_components],
        contracts=contracts.model_dump(mode="json"),
        operator_checklist=checklist.model_dump(mode="json"),
        config=resolved.model_dump(mode="json"),
        metadata=metadata or {},
    )


def export_v1_acceptance_report(
    report: V1AcceptanceReport,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_v1_acceptance_config()
    output_path = Path(path or config.acceptance_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path