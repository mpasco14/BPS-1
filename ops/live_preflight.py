from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from risk.risk_state import RiskStateSnapshot, load_risk_state_snapshot


load_dotenv()


PreflightStatus = Literal["PASS", "WARN", "FAIL"]


class LivePreflightConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_dir: Path = Path("artifacts/ops")

    require_live_safety_pass: bool = True
    require_capital_ramp_pass: bool = True
    require_deployment_readiness_pass: bool = True
    require_testnet_warmup_pass: bool = True
    require_testnet_continuous_pass: bool = False
    require_emergency_state_clear: bool = True
    require_risk_state_ok: bool = True
    require_live_flags_disabled_during_check: bool = True


class LivePreflightInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    live_safety_passed: bool | None = None
    capital_ramp_passed: bool | None = None
    deployment_readiness_passed: bool | None = None
    testnet_warmup_passed: bool | None = None
    testnet_continuous_passed: bool | None = None

    emergency_safe_mode_active: bool = False
    risk_state_status: str | None = None
    risk_state_blockers: list[str] = Field(default_factory=list)

    binance_allow_live_trading: bool = False
    risk_allow_live_trading: bool = False
    binance_execution_mode: str = "paper"


class LivePreflightCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: PreflightStatus
    title: str
    message: str
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class LivePreflightReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_preflight"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

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


def load_live_preflight_config() -> LivePreflightConfig:
    return LivePreflightConfig(
        enabled=env_bool("LIVE_PREFLIGHT_ENABLED", True),
        output_dir=Path(os.getenv("LIVE_PREFLIGHT_OUTPUT_DIR", "artifacts/ops")),
        require_live_safety_pass=env_bool("LIVE_PREFLIGHT_REQUIRE_LIVE_SAFETY_PASS", True),
        require_capital_ramp_pass=env_bool("LIVE_PREFLIGHT_REQUIRE_CAPITAL_RAMP_PASS", True),
        require_deployment_readiness_pass=env_bool("LIVE_PREFLIGHT_REQUIRE_DEPLOYMENT_READINESS_PASS", True),
        require_testnet_warmup_pass=env_bool("LIVE_PREFLIGHT_REQUIRE_TESTNET_WARMUP_PASS", True),
        require_testnet_continuous_pass=env_bool("LIVE_PREFLIGHT_REQUIRE_TESTNET_CONTINUOUS_PASS", False),
        require_emergency_state_clear=env_bool("LIVE_PREFLIGHT_REQUIRE_EMERGENCY_STATE_CLEAR", True),
        require_risk_state_ok=env_bool("LIVE_PREFLIGHT_REQUIRE_RISK_STATE_OK", True),
        require_live_flags_disabled_during_check=env_bool("LIVE_PREFLIGHT_REQUIRE_LIVE_FLAGS_DISABLED_DURING_CHECK", True),
    )


def latest_file(directory: str | Path, pattern: str) -> Path | None:
    path = Path(directory)

    if not path.exists():
        return None

    files = [item for item in path.glob(pattern) if item.is_file()]

    if not files:
        return None

    return max(files, key=lambda item: item.stat().st_mtime)


def load_json(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None

    input_path = Path(path)

    if not input_path.exists():
        return None

    return json.loads(input_path.read_text(encoding="utf-8"))


def make_check(
    *,
    code: str,
    status: PreflightStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> LivePreflightCheck:
    return LivePreflightCheck(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def extract_live_preflight_inputs_from_artifacts() -> LivePreflightInputs:
    live_safety = load_json(latest_file("artifacts/ops", "*live_safety*.json"))
    capital_ramp = load_json(latest_file("artifacts/ops", "*capital_ramp*.json"))
    readiness = load_json(latest_file("artifacts/ops", "*readiness*.json"))
    warmup = load_json(latest_file("artifacts/ops", "*warmup*.json"))
    continuous = load_json(latest_file("artifacts/testnet", "*continuous*.json"))
    emergency = load_json(os.getenv("EMERGENCY_SHUTDOWN_STATE_FILE", "artifacts/ops/emergency_shutdown_state.json"))

    risk_state: RiskStateSnapshot | None = load_risk_state_snapshot()

    return LivePreflightInputs(
        live_safety_passed=(live_safety or {}).get("passed"),
        capital_ramp_passed=(capital_ramp or {}).get("passed"),
        deployment_readiness_passed=(readiness or {}).get("passed"),
        testnet_warmup_passed=(warmup or {}).get("passed"),
        testnet_continuous_passed=(continuous or {}).get("passed"),
        emergency_safe_mode_active=bool((emergency or {}).get("safe_mode_active", False)),
        risk_state_status=risk_state.status if risk_state else None,
        risk_state_blockers=risk_state.blockers if risk_state else [],
        binance_allow_live_trading=env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
        risk_allow_live_trading=env_bool("RISK_ALLOW_LIVE_TRADING", False),
        binance_execution_mode=os.getenv("BINANCE_EXECUTION_MODE", "paper").strip().lower(),
    )


def evaluate_live_preflight(
    *,
    inputs: LivePreflightInputs,
    config: LivePreflightConfig,
) -> list[LivePreflightCheck]:
    if not config.enabled:
        return [
            make_check(
                code="LIVE_PREFLIGHT_DISABLED",
                status="FAIL",
                title="Live preflight desabilitado",
                message="LIVE_PREFLIGHT_ENABLED está falso.",
                value=False,
                expected=True,
                blocking=True,
            )
        ]

    checks: list[LivePreflightCheck] = []

    if config.require_live_flags_disabled_during_check:
        live_enabled = (
            inputs.binance_allow_live_trading
            or inputs.risk_allow_live_trading
            or inputs.binance_execution_mode == "live"
        )

        checks.append(
            make_check(
                code="LIVE_FLAGS_DISABLED" if not live_enabled else "LIVE_FLAGS_ENABLED_DURING_PREFLIGHT",
                status="PASS" if not live_enabled else "FAIL",
                title="Live flags durante preflight",
                message="Live precisa estar desabilitado durante o checklist.",
                value=live_enabled,
                expected=False,
                blocking=live_enabled,
            )
        )

    required = [
        ("LIVE_SAFETY", config.require_live_safety_pass, inputs.live_safety_passed),
        ("CAPITAL_RAMP", config.require_capital_ramp_pass, inputs.capital_ramp_passed),
        ("DEPLOYMENT_READINESS", config.require_deployment_readiness_pass, inputs.deployment_readiness_passed),
        ("TESTNET_WARMUP", config.require_testnet_warmup_pass, inputs.testnet_warmup_passed),
        ("TESTNET_CONTINUOUS", config.require_testnet_continuous_pass, inputs.testnet_continuous_passed),
    ]

    for name, is_required, passed in required:
        if not is_required:
            checks.append(
                make_check(
                    code=f"{name}_NOT_REQUIRED",
                    status="WARN",
                    title=f"{name} não obrigatório",
                    message=f"{name} não está obrigatório pela configuração.",
                    value=passed,
                )
            )
            continue

        checks.append(
            make_check(
                code=f"{name}_PASS" if passed is True else f"{name}_FAIL",
                status="PASS" if passed is True else "FAIL",
                title=f"{name}",
                message=f"Validação {name}.",
                value=passed,
                expected=True,
                blocking=passed is not True,
            )
        )

    if config.require_emergency_state_clear:
        checks.append(
            make_check(
                code="EMERGENCY_STATE_CLEAR" if not inputs.emergency_safe_mode_active else "EMERGENCY_STATE_ACTIVE",
                status="PASS" if not inputs.emergency_safe_mode_active else "FAIL",
                title="Emergency state",
                message="Safe mode precisa estar limpo.",
                value=inputs.emergency_safe_mode_active,
                expected=False,
                blocking=inputs.emergency_safe_mode_active,
            )
        )

    if config.require_risk_state_ok:
        risk_ok = inputs.risk_state_status == "OK"
        checks.append(
            make_check(
                code="RISK_STATE_OK" if risk_ok else "RISK_STATE_NOT_OK",
                status="PASS" if risk_ok else "FAIL",
                title="Risk state",
                message="Estado de risco precisa estar OK.",
                value={
                    "status": inputs.risk_state_status,
                    "blockers": inputs.risk_state_blockers,
                },
                expected="OK",
                blocking=not risk_ok,
            )
        )

    return checks


def build_live_preflight_report(
    *,
    inputs: LivePreflightInputs | dict[str, Any] | None = None,
    config: LivePreflightConfig | None = None,
) -> LivePreflightReport:
    resolved_config = config or load_live_preflight_config()

    if inputs is None:
        resolved_inputs = extract_live_preflight_inputs_from_artifacts()
    elif isinstance(inputs, LivePreflightInputs):
        resolved_inputs = inputs
    else:
        resolved_inputs = LivePreflightInputs.model_validate(inputs)

    checks = evaluate_live_preflight(
        inputs=resolved_inputs,
        config=resolved_config,
    )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0

    return LivePreflightReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        inputs=resolved_inputs.model_dump(mode="json"),
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_live_preflight_report(
    report: LivePreflightReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "live_preflight_latest",
) -> Path:
    config = load_live_preflight_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name.replace('/', '_').replace(chr(92), '_')}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path