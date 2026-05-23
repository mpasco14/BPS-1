from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


RuntimeConfigStatus = Literal["PASS", "WARN", "FAIL"]
ExecutionMode = Literal["paper", "testnet", "live"]


class RuntimeConfigValidatorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/infra")

    environment: str = "development"
    execution_mode: ExecutionMode = "paper"

    require_live_safe_defaults: bool = True
    allow_live: bool = False
    require_dry_run: bool = True
    require_production_guard: bool = True


class RuntimeConfigInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    environment: str = "development"
    execution_mode: str = "paper"

    debug: bool = False

    binance_allow_live_trading: bool = False
    risk_allow_live_trading: bool = False

    live_order_adapter_enabled: bool = False
    live_order_adapter_dry_run: bool = True
    live_order_adapter_allow_submission: bool = False

    production_guard_enabled: bool = True
    kill_switch_enabled: bool = True

    redis_configured: bool = False
    kafka_configured: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeConfigCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: RuntimeConfigStatus
    message: str
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class RuntimeConfigValidationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "runtime_config_validator"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: RuntimeConfigStatus

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


def load_runtime_config_validator_config() -> RuntimeConfigValidatorConfig:
    mode = os.getenv("RUNTIME_CONFIG_EXECUTION_MODE", "paper").strip().lower()

    if mode not in {"paper", "testnet", "live"}:
        mode = "paper"

    return RuntimeConfigValidatorConfig(
        output_dir=Path(os.getenv("RUNTIME_CONFIG_OUTPUT_DIR", "artifacts/infra")),
        environment=os.getenv("RUNTIME_CONFIG_ENVIRONMENT", "development"),
        execution_mode=mode,  # type: ignore[arg-type]
        require_live_safe_defaults=env_bool("RUNTIME_CONFIG_REQUIRE_LIVE_SAFE_DEFAULTS", True),
        allow_live=env_bool("RUNTIME_CONFIG_ALLOW_LIVE", False),
        require_dry_run=env_bool("RUNTIME_CONFIG_REQUIRE_DRY_RUN", True),
        require_production_guard=env_bool("RUNTIME_CONFIG_REQUIRE_PRODUCTION_GUARD", True),
    )


def runtime_inputs_from_env() -> RuntimeConfigInputs:
    return RuntimeConfigInputs(
        environment=os.getenv("RUNTIME_CONFIG_ENVIRONMENT", os.getenv("PRODUCTION_ENVIRONMENT", "development")),
        execution_mode=os.getenv("BINANCE_EXECUTION_MODE", os.getenv("RUNTIME_CONFIG_EXECUTION_MODE", "paper")).strip().lower(),
        debug=env_bool("DEBUG", False),
        binance_allow_live_trading=env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
        risk_allow_live_trading=env_bool("RISK_ALLOW_LIVE_TRADING", False),
        live_order_adapter_enabled=env_bool("LIVE_ORDER_ADAPTER_ENABLED", False),
        live_order_adapter_dry_run=env_bool("LIVE_ORDER_ADAPTER_DRY_RUN", True),
        live_order_adapter_allow_submission=env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
        production_guard_enabled=env_bool("PRODUCTION_GUARD_ENABLED", True),
        kill_switch_enabled=env_bool("KILL_SWITCH_ENABLED", True),
        redis_configured=bool(os.getenv("REDIS_HOST")),
        kafka_configured=bool(os.getenv("KAFKA_HOST")),
    )


def make_check(
    *,
    code: str,
    ok: bool,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = True,
) -> RuntimeConfigCheck:
    return RuntimeConfigCheck(
        code=code if ok else f"{code}_FAILED",
        status="PASS" if ok else "FAIL",
        message=message,
        value=value,
        expected=expected,
        blocking=not ok and blocking,
    )


def warn_check(
    *,
    code: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
) -> RuntimeConfigCheck:
    return RuntimeConfigCheck(
        code=code,
        status="WARN",
        message=message,
        value=value,
        expected=expected,
        blocking=False,
    )


def validate_runtime_config(
    *,
    inputs: RuntimeConfigInputs | dict[str, Any] | None = None,
    config: RuntimeConfigValidatorConfig | None = None,
) -> RuntimeConfigValidationReport:
    resolved_config = config or load_runtime_config_validator_config()
    resolved_inputs = (
        runtime_inputs_from_env()
        if inputs is None
        else inputs if isinstance(inputs, RuntimeConfigInputs)
        else RuntimeConfigInputs.model_validate(inputs)
    )

    checks: list[RuntimeConfigCheck] = []

    checks.append(
        make_check(
            code="VALID_EXECUTION_MODE",
            ok=resolved_inputs.execution_mode in {"paper", "testnet", "live"},
            message="Execution mode precisa ser paper, testnet ou live.",
            value=resolved_inputs.execution_mode,
            expected="paper|testnet|live",
        )
    )

    checks.append(
        make_check(
            code="DEBUG_DISABLED_FOR_NON_DEV",
            ok=resolved_inputs.environment == "development" or not resolved_inputs.debug,
            message="Debug não deve estar ativo fora de development.",
            value=resolved_inputs.debug,
            expected=False,
        )
    )

    if resolved_config.require_production_guard:
        checks.append(
            make_check(
                code="PRODUCTION_GUARD_ENABLED",
                ok=resolved_inputs.production_guard_enabled,
                message="Production guard precisa estar habilitado.",
                value=resolved_inputs.production_guard_enabled,
                expected=True,
            )
        )

    checks.append(
        make_check(
            code="KILL_SWITCH_ENABLED",
            ok=resolved_inputs.kill_switch_enabled,
            message="Kill switch precisa estar habilitado.",
            value=resolved_inputs.kill_switch_enabled,
            expected=True,
        )
    )

    live_intent = (
        resolved_inputs.execution_mode == "live"
        or resolved_inputs.binance_allow_live_trading
        or resolved_inputs.risk_allow_live_trading
        or resolved_inputs.live_order_adapter_enabled
        or resolved_inputs.live_order_adapter_allow_submission
    )

    if live_intent and not resolved_config.allow_live:
        checks.append(
            make_check(
                code="LIVE_NOT_ALLOWED_BY_RUNTIME_CONFIG",
                ok=False,
                message="Live detectado, mas RUNTIME_CONFIG_ALLOW_LIVE=false.",
                value=True,
                expected=False,
            )
        )

    if resolved_config.require_live_safe_defaults:
        checks.append(
            make_check(
                code="BINANCE_LIVE_DISABLED_BY_DEFAULT",
                ok=not resolved_inputs.binance_allow_live_trading or resolved_config.allow_live,
                message="BINANCE_ALLOW_LIVE_TRADING deve ficar false por padrão.",
                value=resolved_inputs.binance_allow_live_trading,
                expected=False,
            )
        )

        checks.append(
            make_check(
                code="RISK_LIVE_DISABLED_BY_DEFAULT",
                ok=not resolved_inputs.risk_allow_live_trading or resolved_config.allow_live,
                message="RISK_ALLOW_LIVE_TRADING deve ficar false por padrão.",
                value=resolved_inputs.risk_allow_live_trading,
                expected=False,
            )
        )

    if resolved_config.require_dry_run:
        checks.append(
            make_check(
                code="LIVE_ORDER_ADAPTER_DRY_RUN",
                ok=resolved_inputs.live_order_adapter_dry_run,
                message="Live order adapter deve iniciar em dry_run.",
                value=resolved_inputs.live_order_adapter_dry_run,
                expected=True,
            )
        )

    if resolved_inputs.live_order_adapter_allow_submission and resolved_inputs.live_order_adapter_dry_run:
        checks.append(
            warn_check(
                code="LIVE_SUBMISSION_TRUE_BUT_DRY_RUN_TRUE",
                message="allow_submission=true mas dry_run=true. A submissão real ainda deve ficar bloqueada.",
                value={
                    "allow_submission": resolved_inputs.live_order_adapter_allow_submission,
                    "dry_run": resolved_inputs.live_order_adapter_dry_run,
                },
            )
        )

    if not resolved_inputs.redis_configured:
        checks.append(
            warn_check(
                code="REDIS_NOT_CONFIGURED",
                message="Redis não configurado. O sistema deve usar fallback local/degradado.",
                value=False,
                expected=True,
            )
        )

    if not resolved_inputs.kafka_configured:
        checks.append(
            warn_check(
                code="KAFKA_NOT_CONFIGURED",
                message="Kafka não configurado. Eventos devem continuar sendo persistidos localmente.",
                value=False,
                expected=True,
            )
        )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.blocking)

    blockers = [item.code for item in checks if item.blocking]
    warnings = [item.code for item in checks if item.status == "WARN"]

    passed = blocking_fail_count == 0

    return RuntimeConfigValidationReport(
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


def export_runtime_config_validation_report(
    report: RuntimeConfigValidationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "runtime_config_validation_latest",
) -> Path:
    config = load_runtime_config_validator_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path