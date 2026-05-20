from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


GovernanceStatus = Literal["PASS", "WARN", "FAIL"]


class GovernanceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/governance")

    require_intelligence: bool = True
    require_traceability: bool = True
    require_discipline: bool = True
    require_security: bool = True
    require_resilience: bool = True


class GovernanceEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Inteligência
    model_available: bool = False
    calibration_available: bool = False
    ood_detection_available: bool = False
    feedback_dataset_available: bool = False

    # Rastreabilidade
    decision_journal_available: bool = False
    order_lifecycle_available: bool = False
    audit_reports_available: bool = False
    model_registry_available: bool = False

    # Disciplina
    risk_manager_available: bool = False
    live_guard_available: bool = False
    capital_ramp_available: bool = False
    preflight_available: bool = False

    # Segurança
    live_disabled_by_default: bool = True
    secrets_not_committed: bool = True
    testnet_separated: bool = True
    compliance_available: bool = False

    # Resiliência
    kill_switch_available: bool = False
    emergency_shutdown_available: bool = False
    health_checks_available: bool = False
    alerting_available: bool = False


class GovernanceCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    pillar: str
    code: str
    status: GovernanceStatus
    title: str
    message: str
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class GovernanceReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "governance"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    checks_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    blocking_fail_count: int

    pillars: dict[str, str] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    checks: list[dict[str, Any]] = Field(default_factory=list)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_governance_config() -> GovernanceConfig:
    return GovernanceConfig(
        output_dir=Path(os.getenv("GOVERNANCE_OUTPUT_DIR", "artifacts/governance")),
        require_intelligence=env_bool("GOVERNANCE_REQUIRE_INTELLIGENCE", True),
        require_traceability=env_bool("GOVERNANCE_REQUIRE_TRACEABILITY", True),
        require_discipline=env_bool("GOVERNANCE_REQUIRE_DISCIPLINE", True),
        require_security=env_bool("GOVERNANCE_REQUIRE_SECURITY", True),
        require_resilience=env_bool("GOVERNANCE_REQUIRE_RESILIENCE", True),
    )


def make_check(
    *,
    pillar: str,
    code: str,
    status: GovernanceStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> GovernanceCheck:
    return GovernanceCheck(
        pillar=pillar,
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def evaluate_pillar(
    *,
    pillar: str,
    required: bool,
    items: dict[str, bool],
) -> list[GovernanceCheck]:
    checks: list[GovernanceCheck] = []

    if not required:
        checks.append(
            make_check(
                pillar=pillar,
                code=f"{pillar.upper()}_NOT_REQUIRED",
                status="WARN",
                title=f"{pillar} não obrigatório",
                message=f"O pilar {pillar} não está obrigatório pela configuração.",
            )
        )
        return checks

    for item_name, item_value in items.items():
        checks.append(
            make_check(
                pillar=pillar,
                code=f"{pillar.upper()}_{item_name.upper()}",
                status="PASS" if item_value else "FAIL",
                title=f"{pillar}: {item_name}",
                message=f"Validação do componente {item_name} no pilar {pillar}.",
                value=item_value,
                expected=True,
                blocking=not item_value,
            )
        )

    return checks


def evaluate_governance(
    *,
    evidence: GovernanceEvidence | dict[str, Any],
    config: GovernanceConfig | None = None,
) -> GovernanceReport:
    resolved_config = config or load_governance_config()
    resolved_evidence = evidence if isinstance(evidence, GovernanceEvidence) else GovernanceEvidence.model_validate(evidence)

    checks: list[GovernanceCheck] = []

    checks.extend(
        evaluate_pillar(
            pillar="intelligence",
            required=resolved_config.require_intelligence,
            items={
                "model_available": resolved_evidence.model_available,
                "calibration_available": resolved_evidence.calibration_available,
                "ood_detection_available": resolved_evidence.ood_detection_available,
                "feedback_dataset_available": resolved_evidence.feedback_dataset_available,
            },
        )
    )

    checks.extend(
        evaluate_pillar(
            pillar="traceability",
            required=resolved_config.require_traceability,
            items={
                "decision_journal_available": resolved_evidence.decision_journal_available,
                "order_lifecycle_available": resolved_evidence.order_lifecycle_available,
                "audit_reports_available": resolved_evidence.audit_reports_available,
                "model_registry_available": resolved_evidence.model_registry_available,
            },
        )
    )

    checks.extend(
        evaluate_pillar(
            pillar="discipline",
            required=resolved_config.require_discipline,
            items={
                "risk_manager_available": resolved_evidence.risk_manager_available,
                "live_guard_available": resolved_evidence.live_guard_available,
                "capital_ramp_available": resolved_evidence.capital_ramp_available,
                "preflight_available": resolved_evidence.preflight_available,
            },
        )
    )

    checks.extend(
        evaluate_pillar(
            pillar="security",
            required=resolved_config.require_security,
            items={
                "live_disabled_by_default": resolved_evidence.live_disabled_by_default,
                "secrets_not_committed": resolved_evidence.secrets_not_committed,
                "testnet_separated": resolved_evidence.testnet_separated,
                "compliance_available": resolved_evidence.compliance_available,
            },
        )
    )

    checks.extend(
        evaluate_pillar(
            pillar="resilience",
            required=resolved_config.require_resilience,
            items={
                "kill_switch_available": resolved_evidence.kill_switch_available,
                "emergency_shutdown_available": resolved_evidence.emergency_shutdown_available,
                "health_checks_available": resolved_evidence.health_checks_available,
                "alerting_available": resolved_evidence.alerting_available,
            },
        )
    )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0

    pillars = {
        pillar: "PASS"
        if all(check.status == "PASS" for check in checks if check.pillar == pillar)
        else "FAIL"
        for pillar in ["intelligence", "traceability", "discipline", "security", "resilience"]
    }

    return GovernanceReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        pillars=pillars,
        evidence=resolved_evidence.model_dump(mode="json"),
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_governance_report(
    report: GovernanceReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "governance_latest",
) -> Path:
    config = load_governance_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path