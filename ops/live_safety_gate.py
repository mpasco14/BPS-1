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


SafetyStatus = Literal["PASS", "WARN", "FAIL"]


class LiveSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_dir: Path = Path("artifacts/ops")

    require_security_pass: bool = True
    require_compliance_no_blocking_fails: bool = True
    require_runbook_pass: bool = True
    require_deployment_readiness_pass: bool = True
    require_testnet_warmup_pass: bool = True
    require_emergency_state_clear: bool = True
    require_legal_review: bool = True

    require_live_disabled_during_check: bool = True
    allow_auto_enable_live: bool = False


class LiveSafetyInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    security_passed: bool | None = None
    compliance_blocking_fail_count: int = 0

    runbook_passed: bool | None = None
    deployment_readiness_passed: bool | None = None
    testnet_warmup_passed: bool | None = None

    emergency_safe_mode_active: bool = False
    legal_review_approved: bool = False

    binance_allow_live_trading: bool = False
    risk_allow_live_trading: bool = False
    binance_execution_mode: str = "paper"


class LiveSafetyCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: SafetyStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class LiveSafetyReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_safety_gate"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str
    live_allowed_by_gate: bool = False
    auto_enable_live_allowed: bool = False

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


def load_live_safety_config() -> LiveSafetyConfig:
    return LiveSafetyConfig(
        enabled=env_bool("LIVE_SAFETY_GATE_ENABLED", True),
        output_dir=Path(os.getenv("LIVE_SAFETY_OUTPUT_DIR", "artifacts/ops")),
        require_security_pass=env_bool("LIVE_SAFETY_REQUIRE_SECURITY_PASS", True),
        require_compliance_no_blocking_fails=env_bool("LIVE_SAFETY_REQUIRE_COMPLIANCE_NO_BLOCKING_FAILS", True),
        require_runbook_pass=env_bool("LIVE_SAFETY_REQUIRE_RUNBOOK_PASS", True),
        require_deployment_readiness_pass=env_bool("LIVE_SAFETY_REQUIRE_DEPLOYMENT_READINESS_PASS", True),
        require_testnet_warmup_pass=env_bool("LIVE_SAFETY_REQUIRE_TESTNET_WARMUP_PASS", True),
        require_emergency_state_clear=env_bool("LIVE_SAFETY_REQUIRE_EMERGENCY_STATE_CLEAR", True),
        require_legal_review=env_bool("LIVE_SAFETY_REQUIRE_LEGAL_REVIEW", True),
        require_live_disabled_during_check=env_bool("LIVE_SAFETY_REQUIRE_LIVE_DISABLED_DURING_CHECK", True),
        allow_auto_enable_live=env_bool("LIVE_SAFETY_ALLOW_AUTO_ENABLE_LIVE", False),
    )


def make_check(
    *,
    code: str,
    status: SafetyStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> LiveSafetyCheck:
    return LiveSafetyCheck(
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


def extract_live_safety_inputs_from_artifacts() -> LiveSafetyInputs:
    security = run_security_checks()
    compliance = run_compliance_checks()

    runbook = load_json(latest_file("artifacts/ops", "*runbook*.json"))
    readiness = load_json(latest_file("artifacts/ops", "*readiness*.json"))
    warmup = load_json(latest_file("artifacts/ops", "*warmup*.json"))
    emergency = load_json(
        Path(os.getenv("EMERGENCY_SHUTDOWN_STATE_FILE", "artifacts/ops/emergency_shutdown_state.json"))
    )

    return LiveSafetyInputs(
        security_passed=security.passed,
        compliance_blocking_fail_count=compliance.blocking_fail_count,
        runbook_passed=(runbook or {}).get("passed"),
        deployment_readiness_passed=(readiness or {}).get("passed"),
        testnet_warmup_passed=(warmup or {}).get("passed"),
        emergency_safe_mode_active=bool((emergency or {}).get("safe_mode_active", False)),
        legal_review_approved=env_bool("OPS_LEGAL_REVIEW_APPROVED", False),
        binance_allow_live_trading=env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
        risk_allow_live_trading=env_bool("RISK_ALLOW_LIVE_TRADING", False),
        binance_execution_mode=os.getenv("BINANCE_EXECUTION_MODE", "paper").strip().lower(),
    )


def evaluate_live_safety(
    *,
    inputs: LiveSafetyInputs,
    config: LiveSafetyConfig,
) -> list[LiveSafetyCheck]:
    if not config.enabled:
        return [
            make_check(
                code="LIVE_SAFETY_GATE_DISABLED",
                status="FAIL",
                title="Live safety gate desabilitado",
                message="LIVE_SAFETY_GATE_ENABLED está falso.",
                value=False,
                expected=True,
                blocking=True,
            )
        ]

    checks: list[LiveSafetyCheck] = []

    live_enabled = (
        inputs.binance_allow_live_trading
        or inputs.risk_allow_live_trading
        or inputs.binance_execution_mode == "live"
    )

    if config.require_live_disabled_during_check:
        if live_enabled:
            checks.append(
                make_check(
                    code="LIVE_ENABLED_DURING_SAFETY_CHECK",
                    status="FAIL",
                    title="Live habilitado durante safety check",
                    message="Live precisa estar desabilitado durante a avaliação.",
                    value={
                        "BINANCE_ALLOW_LIVE_TRADING": inputs.binance_allow_live_trading,
                        "RISK_ALLOW_LIVE_TRADING": inputs.risk_allow_live_trading,
                        "BINANCE_EXECUTION_MODE": inputs.binance_execution_mode,
                    },
                    expected="live disabled",
                    blocking=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code="LIVE_DISABLED_DURING_SAFETY_CHECK",
                    status="PASS",
                    title="Live desabilitado durante safety check",
                    message="Flags de live estão seguras durante o check.",
                    value=False,
                    expected=False,
                )
            )

    required_checks = [
        ("SECURITY", config.require_security_pass, inputs.security_passed is True),
        ("RUNBOOK", config.require_runbook_pass, inputs.runbook_passed is True),
        ("DEPLOYMENT_READINESS", config.require_deployment_readiness_pass, inputs.deployment_readiness_passed is True),
        ("TESTNET_WARMUP", config.require_testnet_warmup_pass, inputs.testnet_warmup_passed is True),
    ]

    for name, required, passed in required_checks:
        if not required:
            checks.append(
                make_check(
                    code=f"{name}_NOT_REQUIRED",
                    status="WARN",
                    title=f"{name} não obrigatório",
                    message=f"Check {name} não é obrigatório pela configuração.",
                )
            )
            continue

        if passed:
            checks.append(
                make_check(
                    code=f"{name}_PASS",
                    status="PASS",
                    title=f"{name} aprovado",
                    message=f"{name} passou.",
                    value=True,
                    expected=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code=f"{name}_FAIL",
                    status="FAIL",
                    title=f"{name} não aprovado",
                    message=f"{name} falhou ou está ausente.",
                    value=False,
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
                    title="Compliance sem bloqueios",
                    message="Compliance não possui falhas bloqueantes.",
                    value=0,
                    expected=0,
                )
            )
        else:
            checks.append(
                make_check(
                    code="COMPLIANCE_BLOCKING_FAILS",
                    status="FAIL",
                    title="Compliance bloqueante",
                    message="Compliance possui falhas bloqueantes.",
                    value=inputs.compliance_blocking_fail_count,
                    expected=0,
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
                    message="Existe estado de emergência ativo.",
                    value=True,
                    expected=False,
                    blocking=True,
                )
            )

    if config.require_legal_review:
        if inputs.legal_review_approved:
            checks.append(
                make_check(
                    code="LEGAL_REVIEW_APPROVED",
                    status="PASS",
                    title="Revisão jurídica aprovada",
                    message="Revisão jurídica está aprovada.",
                    value=True,
                    expected=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code="LEGAL_REVIEW_REQUIRED",
                    status="FAIL",
                    title="Revisão jurídica obrigatória",
                    message="Live trading não deve ser considerado sem parecer jurídico formal.",
                    value=False,
                    expected=True,
                    blocking=True,
                )
            )

    return checks


def build_live_safety_report(
    *,
    inputs: LiveSafetyInputs | dict[str, Any] | None = None,
    config: LiveSafetyConfig | None = None,
) -> LiveSafetyReport:
    resolved_config = config or load_live_safety_config()

    if inputs is None:
        resolved_inputs = extract_live_safety_inputs_from_artifacts()
    elif isinstance(inputs, LiveSafetyInputs):
        resolved_inputs = inputs
    else:
        resolved_inputs = LiveSafetyInputs.model_validate(inputs)

    checks = evaluate_live_safety(
        inputs=resolved_inputs,
        config=resolved_config,
    )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0

    return LiveSafetyReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        live_allowed_by_gate=passed,
        auto_enable_live_allowed=passed and resolved_config.allow_auto_enable_live,
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        inputs=resolved_inputs.model_dump(mode="json"),
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_live_safety_report(
    report: LiveSafetyReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "live_safety_latest",
) -> Path:
    config = load_live_safety_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path