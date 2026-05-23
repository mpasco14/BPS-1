from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ProductionGuardStatus = Literal["PASS", "WARN", "FAIL"]


class ProductionEnvironmentGuardConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/production")

    enabled: bool = True
    environment: str = "production"

    require_testnet_pass: bool = True
    require_live_preflight: bool = True
    require_risk_audit: bool = True
    require_capital_ramp: bool = True
    require_secrets_audit: bool = True
    require_human_approval: bool = True
    require_emergency_clear: bool = True
    allow_debug: bool = False


class ProductionEnvironmentInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    environment: str = "production"
    debug_mode: bool = False

    testnet_passed: bool = False
    live_preflight_passed: bool = False
    live_risk_audit_passed: bool = False
    capital_ramp_validated: bool = False
    secrets_audit_passed: bool = False
    human_approval_valid: bool = False
    emergency_state_clear: bool = True

    binance_execution_mode: str = "paper"
    binance_allow_live_trading: bool = False
    risk_allow_live_trading: bool = False
    live_order_adapter_enabled: bool = False
    live_order_submission_allowed: bool = False


class ProductionEnvironmentCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: ProductionGuardStatus
    message: str
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class ProductionEnvironmentGuardReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "production_environment_guard"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: ProductionGuardStatus

    checks_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    blocking_fail_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    inputs: dict[str, Any]
    checks: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_production_environment_guard_config() -> ProductionEnvironmentGuardConfig:
    return ProductionEnvironmentGuardConfig(
        output_dir=Path(os.getenv("PRODUCTION_GUARD_OUTPUT_DIR", "artifacts/production")),
        enabled=env_bool("PRODUCTION_GUARD_ENABLED", True),
        environment=os.getenv("PRODUCTION_ENVIRONMENT", "production"),
        require_testnet_pass=env_bool("PRODUCTION_GUARD_REQUIRE_TESTNET_PASS", True),
        require_live_preflight=env_bool("PRODUCTION_GUARD_REQUIRE_LIVE_PREFLIGHT", True),
        require_risk_audit=env_bool("PRODUCTION_GUARD_REQUIRE_RISK_AUDIT", True),
        require_capital_ramp=env_bool("PRODUCTION_GUARD_REQUIRE_CAPITAL_RAMP", True),
        require_secrets_audit=env_bool("PRODUCTION_GUARD_REQUIRE_SECRETS_AUDIT", True),
        require_human_approval=env_bool("PRODUCTION_GUARD_REQUIRE_HUMAN_APPROVAL", True),
        require_emergency_clear=env_bool("PRODUCTION_GUARD_REQUIRE_EMERGENCY_CLEAR", True),
        allow_debug=env_bool("PRODUCTION_GUARD_ALLOW_DEBUG", False),
    )


def inputs_from_environment() -> ProductionEnvironmentInputs:
    return ProductionEnvironmentInputs(
        environment=os.getenv("PRODUCTION_ENVIRONMENT", "production"),
        debug_mode=env_bool("DEBUG", False),
        binance_execution_mode=os.getenv("BINANCE_EXECUTION_MODE", "paper").strip().lower(),
        binance_allow_live_trading=env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
        risk_allow_live_trading=env_bool("RISK_ALLOW_LIVE_TRADING", False),
        live_order_adapter_enabled=env_bool("LIVE_ORDER_ADAPTER_ENABLED", False),
        live_order_submission_allowed=env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
    )


def check(
    code: str,
    ok: bool,
    message: str,
    *,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = True,
) -> ProductionEnvironmentCheck:
    return ProductionEnvironmentCheck(
        code=code if ok else f"{code}_FAILED",
        status="PASS" if ok else "FAIL",
        message=message,
        value=value,
        expected=expected,
        blocking=not ok and blocking,
    )


def evaluate_production_environment_guard(
    *,
    inputs: ProductionEnvironmentInputs | dict[str, Any] | None = None,
    config: ProductionEnvironmentGuardConfig | None = None,
) -> ProductionEnvironmentGuardReport:
    resolved_config = config or load_production_environment_guard_config()

    resolved_inputs = (
        inputs_from_environment()
        if inputs is None
        else inputs if isinstance(inputs, ProductionEnvironmentInputs)
        else ProductionEnvironmentInputs.model_validate(inputs)
    )

    checks: list[ProductionEnvironmentCheck] = []

    checks.append(
        check(
            "PRODUCTION_GUARD_ENABLED",
            resolved_config.enabled,
            "Production guard precisa estar habilitado.",
            value=resolved_config.enabled,
            expected=True,
        )
    )

    checks.append(
        check(
            "ENVIRONMENT_MATCH",
            resolved_inputs.environment == resolved_config.environment,
            "Ambiente informado precisa bater com a configuração esperada.",
            value=resolved_inputs.environment,
            expected=resolved_config.environment,
        )
    )

    checks.append(
        check(
            "DEBUG_DISABLED",
            resolved_config.allow_debug or not resolved_inputs.debug_mode,
            "Debug precisa estar desabilitado em produção.",
            value=resolved_inputs.debug_mode,
            expected=False,
        )
    )

    requirements = [
        ("TESTNET_PASS", resolved_config.require_testnet_pass, resolved_inputs.testnet_passed),
        ("LIVE_PREFLIGHT_PASS", resolved_config.require_live_preflight, resolved_inputs.live_preflight_passed),
        ("LIVE_RISK_AUDIT_PASS", resolved_config.require_risk_audit, resolved_inputs.live_risk_audit_passed),
        ("CAPITAL_RAMP_VALIDATED", resolved_config.require_capital_ramp, resolved_inputs.capital_ramp_validated),
        ("SECRETS_AUDIT_PASS", resolved_config.require_secrets_audit, resolved_inputs.secrets_audit_passed),
        ("HUMAN_APPROVAL_VALID", resolved_config.require_human_approval, resolved_inputs.human_approval_valid),
        ("EMERGENCY_CLEAR", resolved_config.require_emergency_clear, resolved_inputs.emergency_state_clear),
    ]

    for code_name, required, value in requirements:
        if not required:
            checks.append(
                ProductionEnvironmentCheck(
                    code=f"{code_name}_NOT_REQUIRED",
                    status="WARN",
                    message=f"{code_name} não obrigatório pela configuração.",
                    value=value,
                    expected=True,
                    blocking=False,
                )
            )
            continue

        checks.append(
            check(
                code_name,
                value is True,
                f"{code_name} precisa estar aprovado.",
                value=value,
                expected=True,
            )
        )

    live_flags_enabled = (
        resolved_inputs.binance_execution_mode == "live"
        or resolved_inputs.binance_allow_live_trading
        or resolved_inputs.risk_allow_live_trading
        or resolved_inputs.live_order_adapter_enabled
        or resolved_inputs.live_order_submission_allowed
    )

    if live_flags_enabled:
        checks.append(
            ProductionEnvironmentCheck(
                code="LIVE_FLAGS_ENABLED",
                status="WARN",
                message="Flags live já estão habilitadas. Confirme que isso é intencional e aprovado.",
                value={
                    "binance_execution_mode": resolved_inputs.binance_execution_mode,
                    "binance_allow_live_trading": resolved_inputs.binance_allow_live_trading,
                    "risk_allow_live_trading": resolved_inputs.risk_allow_live_trading,
                    "live_order_adapter_enabled": resolved_inputs.live_order_adapter_enabled,
                    "live_order_submission_allowed": resolved_inputs.live_order_submission_allowed,
                },
                expected="manual_approval_required",
                blocking=False,
            )
        )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.blocking)

    blockers = [item.code for item in checks if item.blocking]
    warnings = [item.code for item in checks if item.status == "WARN"]

    passed = blocking_fail_count == 0

    return ProductionEnvironmentGuardReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        blockers=blockers,
        warnings=warnings,
        inputs=resolved_inputs.model_dump(mode="json"),
        checks=[item.model_dump(mode="json") for item in checks],
        config=resolved_config.model_dump(mode="json"),
    )


def export_production_environment_guard_report(
    report: ProductionEnvironmentGuardReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "production_environment_guard_latest",
) -> Path:
    config = load_production_environment_guard_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path