from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from quality.ci_quality_gate import QualityGateReport


load_dotenv()


ReleaseReadinessStatus = Literal["READY", "WARN", "BLOCKED"]


class ReleaseReadinessConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/quality")

    require_ci_pass: bool = True
    require_security_pass: bool = True
    require_infra_pass: bool = True
    require_docs: bool = True
    require_git_clean: bool = True


class ReleaseReadinessInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "unversioned"

    ci_passed: bool = False
    security_passed: bool = False
    infra_passed: bool = False
    docs_present: bool = False
    git_clean: bool = False

    tests_count: int | None = None
    warnings_count: int = 0

    metadata: dict[str, Any] = Field(default_factory=dict)


class ReleaseReadinessReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "release_readiness"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    version: str
    status: ReleaseReadinessStatus
    ready: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    inputs: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_release_readiness_config() -> ReleaseReadinessConfig:
    return ReleaseReadinessConfig(
        output_dir=Path(os.getenv("RELEASE_READINESS_OUTPUT_DIR", "artifacts/quality")),
        require_ci_pass=env_bool("RELEASE_READINESS_REQUIRE_CI_PASS", True),
        require_security_pass=env_bool("RELEASE_READINESS_REQUIRE_SECURITY_PASS", True),
        require_infra_pass=env_bool("RELEASE_READINESS_REQUIRE_INFRA_PASS", True),
        require_docs=env_bool("RELEASE_READINESS_REQUIRE_DOCS", True),
        require_git_clean=env_bool("RELEASE_READINESS_REQUIRE_GIT_CLEAN", True),
    )


def git_worktree_clean() -> bool:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:
        return False

    return completed.returncode == 0 and completed.stdout.strip() == ""


def required_docs_present() -> bool:
    required = [
        "docs/ARCHITECTURE.md",
        "docs/LOCAL_SETUP_RUNBOOK.md",
        "docs/PAPER_TESTNET_RUNBOOK.md",
        "docs/CONTROLLED_LIVE_ACTIVATION_RUNBOOK.md",
        "docs/EMERGENCY_SHUTDOWN_RUNBOOK.md",
        "docs/WEEKLY_AUDIT_RUNBOOK.md",
    ]

    return all(Path(path).exists() for path in required)


def inputs_from_quality_gate(
    *,
    quality_gate: QualityGateReport | dict[str, Any],
    version: str = "unversioned",
) -> ReleaseReadinessInputs:
    gate = quality_gate if isinstance(quality_gate, QualityGateReport) else QualityGateReport.model_validate(quality_gate)

    security_passed = not any("security" in item for item in gate.blockers)
    infra_passed = not any("runtime" in item or "failure" in item for item in gate.blockers)

    return ReleaseReadinessInputs(
        version=version,
        ci_passed=gate.passed,
        security_passed=security_passed,
        infra_passed=infra_passed,
        docs_present=required_docs_present(),
        git_clean=git_worktree_clean(),
        warnings_count=len(gate.warnings),
        metadata={
            "quality_gate_status": gate.status,
            "quality_gate_blockers": gate.blockers,
            "quality_gate_warnings": gate.warnings,
        },
    )


def evaluate_release_readiness(
    *,
    inputs: ReleaseReadinessInputs | dict[str, Any],
    config: ReleaseReadinessConfig | None = None,
) -> ReleaseReadinessReport:
    resolved_config = config or load_release_readiness_config()
    resolved_inputs = inputs if isinstance(inputs, ReleaseReadinessInputs) else ReleaseReadinessInputs.model_validate(inputs)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved_config.require_ci_pass and not resolved_inputs.ci_passed:
        blockers.append("ci_not_passed")
        recommendations.append("Rodar quality gate completo antes de release.")

    if resolved_config.require_security_pass and not resolved_inputs.security_passed:
        blockers.append("security_not_passed")
        recommendations.append("Corrigir findings de segurança antes de release.")

    if resolved_config.require_infra_pass and not resolved_inputs.infra_passed:
        blockers.append("infra_not_passed")
        recommendations.append("Corrigir validações de infraestrutura antes de release.")

    if resolved_config.require_docs and not resolved_inputs.docs_present:
        blockers.append("docs_missing")
        recommendations.append("Atualizar documentação operacional antes de release.")

    if resolved_config.require_git_clean and not resolved_inputs.git_clean:
        blockers.append("git_worktree_not_clean")
        recommendations.append("Commitar ou descartar mudanças antes de release.")

    if resolved_inputs.warnings_count > 0:
        warnings.append("quality_gate_has_warnings")
        recommendations.append("Revisar warnings antes de promover versão.")

    ready = not blockers

    return ReleaseReadinessReport(
        version=resolved_inputs.version,
        status="READY" if ready and not warnings else "WARN" if ready else "BLOCKED",
        ready=ready,
        blockers=blockers,
        warnings=warnings,
        recommendations=recommendations,
        inputs=resolved_inputs.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_release_readiness_report(
    report: ReleaseReadinessReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "release_readiness_latest",
) -> Path:
    config = load_release_readiness_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path