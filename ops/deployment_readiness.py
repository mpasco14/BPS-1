"""
Deployment readiness gate.

Responsabilidades:
- Consolidar security, compliance, runbook, testnet warm-up e emergency state.
- Avaliar readiness para paper/testnet/live.
- Bloquear live quando critérios mínimos falharem.
- Não habilita live trading.
- Não executa ordens.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ops.compliance_check import run_compliance_checks
from ops.security_check import run_security_checks


load_dotenv()


DeploymentStage = Literal["paper", "testnet", "live"]
ReadinessStatus = Literal["PASS", "WARN", "FAIL"]


class DeploymentReadinessConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_dir: Path = Path("artifacts/ops")

    default_stage: DeploymentStage = "testnet"

    require_security_pass: bool = True
    require_compliance_no_blocking_fails: bool = True
    require_runbook_pass: bool = True
    require_testnet_warmup_pass_for_live: bool = True
    require_emergency_state_clear: bool = True
    require_live_disabled_during_check: bool = True


class DeploymentReadinessInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    security_passed: bool | None = None
    compliance_passed: bool | None = None
    compliance_blocking_fail_count: int = 0

    runbook_passed: bool | None = None
    testnet_warmup_passed: bool | None = None

    emergency_safe_mode_active: bool = False

    binance_allow_live_trading: bool = False
    risk_allow_live_trading: bool = False
    binance_execution_mode: str = "paper"

    legal_review_approved: bool = False


class DeploymentReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: ReadinessStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class DeploymentReadinessReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "deployment_readiness"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    stage: DeploymentStage
    passed: bool
    status: str

    live_allowed_by_gate: bool = False

    checks_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    blocking_fail_count: int

    inputs: dict[str, Any]
    checks: list[dict[str, Any]] = Field(default_factory=list)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_deployment_readiness_config() -> DeploymentReadinessConfig:
    stage = os.getenv("DEPLOYMENT_READINESS_DEFAULT_STAGE", "testnet").strip().lower()

    if stage not in {"paper", "testnet", "live"}:
        stage = "testnet"

    return DeploymentReadinessConfig(
        enabled=env_bool("DEPLOYMENT_READINESS_ENABLED", True),
        output_dir=Path(os.getenv("DEPLOYMENT_READINESS_OUTPUT_DIR", "artifacts/ops")),
        default_stage=stage,  # type: ignore[arg-type]
        require_security_pass=env_bool("DEPLOYMENT_REQUIRE_SECURITY_PASS", True),
        require_compliance_no_blocking_fails=env_bool("DEPLOYMENT_REQUIRE_COMPLIANCE_NO_BLOCKING_FAILS", True),
        require_runbook_pass=env_bool("DEPLOYMENT_REQUIRE_RUNBOOK_PASS", True),
        require_testnet_warmup_pass_for_live=env_bool("DEPLOYMENT_REQUIRE_TESTNET_WARMUP_PASS_FOR_LIVE", True),
        require_emergency_state_clear=env_bool("DEPLOYMENT_REQUIRE_EMERGENCY_STATE_CLEAR", True),
        require_live_disabled_during_check=env_bool("DEPLOYMENT_REQUIRE_LIVE_DISABLED_DURING_CHECK", True),
    )


def make_check(
    *,
    code: str,
    status: ReadinessStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> DeploymentReadinessCheck:
    return DeploymentReadinessCheck(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def latest_file(directory: str | Path, pattern: str) -> Path | None:
    path = Path(directory)

    if not path.exists():
        return None

    files = [item for item in path.glob(pattern) if item.is_file()]

    if not files:
        return None

    return max(files, key=lambda item: item.stat().st_mtime)


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def extract_inputs_from_artifacts() -> DeploymentReadinessInputs:
    security = run_security_checks()
    compliance = run_compliance_checks()

    runbook = load_json(latest_file("artifacts/ops", "*runbook*.json"))
    warmup = load_json(latest_file("artifacts/ops", "*warmup*.json"))
    emergency_state = load_json(Path(os.getenv("EMERGENCY_SHUTDOWN_STATE_FILE", "artifacts/ops/emergency_shutdown_state.json")))

    return DeploymentReadinessInputs(
        security_passed=security.passed,
        compliance_passed=compliance.passed,
        compliance_blocking_fail_count=compliance.blocking_fail_count,
        runbook_passed=(runbook or {}).get("passed"),
        testnet_warmup_passed=(warmup or {}).get("passed"),
        emergency_safe_mode_active=bool((emergency_state or {}).get("safe_mode_active", False)),
        binance_allow_live_trading=env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
        risk_allow_live_trading=env_bool("RISK_ALLOW_LIVE_TRADING", False),
        binance_execution_mode=os.getenv("BINANCE_EXECUTION_MODE", "paper").strip().lower(),
        legal_review_approved=env_bool("OPS_LEGAL_REVIEW_APPROVED", False),
    )


def evaluate_deployment_readiness(
    *,
    stage: DeploymentStage,
    inputs: DeploymentReadinessInputs,
    config: DeploymentReadinessConfig,
) -> list[DeploymentReadinessCheck]:
    if not config.enabled:
        return [
            make_check(
                code="DEPLOYMENT_READINESS_DISABLED",
                status="FAIL",
                title="Deployment readiness desabilitado",
                message="DEPLOYMENT_READINESS_ENABLED está falso.",
                value=False,
                expected=True,
                blocking=True,
            )
        ]

    checks: list[DeploymentReadinessCheck] = []

    if config.require_live_disabled_during_check:
        live_enabled = (
            inputs.binance_allow_live_trading
            or inputs.risk_allow_live_trading
            or inputs.binance_execution_mode == "live"
        )

        if live_enabled:
            checks.append(
                make_check(
                    code="LIVE_ENABLED_DURING_READINESS_CHECK",
                    status="FAIL",
                    title="Live trading habilitado durante readiness check",
                    message="Live precisa permanecer desabilitado durante o readiness check.",
                    value={
                        "binance_allow_live_trading": inputs.binance_allow_live_trading,
                        "risk_allow_live_trading": inputs.risk_allow_live_trading,
                        "binance_execution_mode": inputs.binance_execution_mode,
                    },
                    expected="live disabled",
                    blocking=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code="LIVE_DISABLED_DURING_READINESS_CHECK",
                    status="PASS",
                    title="Live trading desabilitado",
                    message="Flags de live trading permanecem seguras.",
                    value={
                        "binance_allow_live_trading": inputs.binance_allow_live_trading,
                        "risk_allow_live_trading": inputs.risk_allow_live_trading,
                        "binance_execution_mode": inputs.binance_execution_mode,
                    },
                )
            )

    if config.require_security_pass:
        if inputs.security_passed is True:
            checks.append(
                make_check(
                    code="SECURITY_READY",
                    status="PASS",
                    title="Security check aprovado",
                    message="Security check passou.",
                    value=True,
                    expected=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code="SECURITY_NOT_READY",
                    status="FAIL",
                    title="Security check não aprovado",
                    message="Security check falhou ou está ausente.",
                    value=inputs.security_passed,
                    expected=True,
                    blocking=True,
                )
            )

    if config.require_compliance_no_blocking_fails:
        if inputs.compliance_blocking_fail_count == 0:
            checks.append(
                make_check(
                    code="COMPLIANCE_NO_BLOCKING_FAILS",
                    status="PASS",
                    title="Compliance sem falhas bloqueantes",
                    message="Compliance check não possui falhas bloqueantes.",
                    value=inputs.compliance_blocking_fail_count,
                    expected=0,
                )
            )
        else:
            checks.append(
                make_check(
                    code="COMPLIANCE_BLOCKING_FAILS",
                    status="FAIL",
                    title="Compliance possui falhas bloqueantes",
                    message="Falhas bloqueantes de compliance impedem avanço.",
                    value=inputs.compliance_blocking_fail_count,
                    expected=0,
                    blocking=True,
                )
            )

    if config.require_runbook_pass:
        if inputs.runbook_passed is True:
            checks.append(
                make_check(
                    code="RUNBOOK_READY",
                    status="PASS",
                    title="Runbook aprovado",
                    message="Runbook operacional passou.",
                    value=True,
                    expected=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code="RUNBOOK_NOT_READY",
                    status="FAIL" if stage == "live" else "WARN",
                    title="Runbook não aprovado",
                    message="Runbook operacional não passou ou está ausente.",
                    value=inputs.runbook_passed,
                    expected=True,
                    blocking=(stage == "live"),
                )
            )

    if stage == "live" and config.require_testnet_warmup_pass_for_live:
        if inputs.testnet_warmup_passed is True:
            checks.append(
                make_check(
                    code="TESTNET_WARMUP_READY_FOR_LIVE",
                    status="PASS",
                    title="Warm-up testnet aprovado",
                    message="Testnet warm-up passou.",
                    value=True,
                    expected=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code="TESTNET_WARMUP_NOT_READY_FOR_LIVE",
                    status="FAIL",
                    title="Warm-up testnet não aprovado",
                    message="Live não pode avançar sem warm-up testnet aprovado.",
                    value=inputs.testnet_warmup_passed,
                    expected=True,
                    blocking=True,
                )
            )

    if stage == "live":
        if inputs.legal_review_approved:
            checks.append(
                make_check(
                    code="LEGAL_REVIEW_READY_FOR_LIVE",
                    status="PASS",
                    title="Revisão jurídica aprovada",
                    message="Revisão jurídica aprovada.",
                    value=True,
                    expected=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code="LEGAL_REVIEW_REQUIRED_FOR_LIVE",
                    status="FAIL",
                    title="Revisão jurídica obrigatória",
                    message="Live trading não deve ser considerado sem parecer jurídico formal.",
                    value=False,
                    expected=True,
                    blocking=True,
                )
            )

    if config.require_emergency_state_clear:
        if not inputs.emergency_safe_mode_active:
            checks.append(
                make_check(
                    code="EMERGENCY_STATE_CLEAR",
                    status="PASS",
                    title="Safe mode limpo",
                    message="Nenhum estado de emergência ativo.",
                    value=False,
                    expected=False,
                )
            )
        else:
            checks.append(
                make_check(
                    code="EMERGENCY_STATE_ACTIVE",
                    status="FAIL",
                    title="Safe mode ativo",
                    message="Existe estado de emergência ativo; deploy deve permanecer bloqueado.",
                    value=True,
                    expected=False,
                    blocking=True,
                )
            )

    return checks


def build_deployment_readiness_report(
    *,
    stage: DeploymentStage | None = None,
    inputs: DeploymentReadinessInputs | dict[str, Any] | None = None,
    config: DeploymentReadinessConfig | None = None,
) -> DeploymentReadinessReport:
    resolved_config = config or load_deployment_readiness_config()
    resolved_stage = stage or resolved_config.default_stage

    if inputs is None:
        resolved_inputs = extract_inputs_from_artifacts()
    elif isinstance(inputs, DeploymentReadinessInputs):
        resolved_inputs = inputs
    else:
        resolved_inputs = DeploymentReadinessInputs.model_validate(inputs)

    checks = evaluate_deployment_readiness(
        stage=resolved_stage,
        inputs=resolved_inputs,
        config=resolved_config,
    )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0
    live_allowed_by_gate = passed and resolved_stage == "live"

    return DeploymentReadinessReport(
        stage=resolved_stage,
        passed=passed,
        status="PASS" if passed else "FAIL",
        live_allowed_by_gate=live_allowed_by_gate,
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        inputs=resolved_inputs.model_dump(mode="json"),
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_deployment_readiness_report(
    report: DeploymentReadinessReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "deployment_readiness_latest",
) -> Path:
    config = load_deployment_readiness_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path