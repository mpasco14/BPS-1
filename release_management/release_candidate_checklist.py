from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ReleaseCandidateStatus = Literal["PASS", "WARN", "FAIL"]


class ReleaseCandidateConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/release")

    require_quality_gate: bool = True
    require_security: bool = True
    require_infra: bool = True
    require_docs: bool = True
    require_version_manifest: bool = True
    require_changelog: bool = True


class ReleaseCandidateInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str

    quality_gate_passed: bool = False
    tests_passed: bool = False
    security_passed: bool = False
    infra_passed: bool = False

    docs_present: bool = False
    changelog_present: bool = False
    version_manifest_present: bool = False

    model_pinned: bool = False
    config_pinned: bool = False
    deployment_plan_present: bool = False

    git_clean: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)


class ReleaseCandidateChecklistReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "release_candidate_checklist"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    version: str
    status: ReleaseCandidateStatus
    passed: bool

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


def load_release_candidate_config() -> ReleaseCandidateConfig:
    return ReleaseCandidateConfig(
        output_dir=Path(os.getenv("RELEASE_CANDIDATE_OUTPUT_DIR", "artifacts/release")),
        require_quality_gate=env_bool("RELEASE_CANDIDATE_REQUIRE_QUALITY_GATE", True),
        require_security=env_bool("RELEASE_CANDIDATE_REQUIRE_SECURITY", True),
        require_infra=env_bool("RELEASE_CANDIDATE_REQUIRE_INFRA", True),
        require_docs=env_bool("RELEASE_CANDIDATE_REQUIRE_DOCS", True),
        require_version_manifest=env_bool("RELEASE_CANDIDATE_REQUIRE_VERSION_MANIFEST", True),
        require_changelog=env_bool("RELEASE_CANDIDATE_REQUIRE_CHANGELOG", True),
    )


def evaluate_release_candidate_checklist(
    *,
    inputs: ReleaseCandidateInputs | dict[str, Any],
    config: ReleaseCandidateConfig | None = None,
) -> ReleaseCandidateChecklistReport:
    resolved_config = config or load_release_candidate_config()
    resolved_inputs = inputs if isinstance(inputs, ReleaseCandidateInputs) else ReleaseCandidateInputs.model_validate(inputs)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved_config.require_quality_gate and not resolved_inputs.quality_gate_passed:
        blockers.append("quality_gate_not_passed")
        recommendations.append("Rodar scripts/run_quality_gate.py antes de gerar release candidate.")

    if not resolved_inputs.tests_passed:
        blockers.append("tests_not_passed")
        recommendations.append("Corrigir testes antes do release candidate.")

    if resolved_config.require_security and not resolved_inputs.security_passed:
        blockers.append("security_not_passed")
        recommendations.append("Corrigir auditoria de segurança antes do release candidate.")

    if resolved_config.require_infra and not resolved_inputs.infra_passed:
        blockers.append("infra_not_passed")
        recommendations.append("Corrigir validações de infraestrutura antes do release candidate.")

    if resolved_config.require_docs and not resolved_inputs.docs_present:
        blockers.append("docs_missing")
        recommendations.append("Atualizar docs e runbooks antes do release candidate.")

    if resolved_config.require_changelog and not resolved_inputs.changelog_present:
        blockers.append("changelog_missing")
        recommendations.append("Gerar changelog antes do release candidate.")

    if resolved_config.require_version_manifest and not resolved_inputs.version_manifest_present:
        blockers.append("version_manifest_missing")
        recommendations.append("Gerar version manifest antes do release candidate.")

    if not resolved_inputs.model_pinned:
        blockers.append("model_not_pinned")
        recommendations.append("Fixar versão do modelo usado pela release.")

    if not resolved_inputs.config_pinned:
        blockers.append("config_not_pinned")
        recommendations.append("Fixar versão/hash da configuração usada pela release.")

    if not resolved_inputs.deployment_plan_present:
        warnings.append("deployment_plan_missing")
        recommendations.append("Criar plano de promoção antes de deploy operacional.")

    if not resolved_inputs.git_clean:
        blockers.append("git_worktree_not_clean")
        recommendations.append("Commitar ou descartar mudanças antes do release candidate.")

    passed = not blockers

    return ReleaseCandidateChecklistReport(
        version=resolved_inputs.version,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        blockers=blockers,
        warnings=warnings,
        recommendations=recommendations,
        inputs=resolved_inputs.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_release_candidate_checklist_report(
    report: ReleaseCandidateChecklistReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "release_candidate_checklist_latest",
) -> Path:
    config = load_release_candidate_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path