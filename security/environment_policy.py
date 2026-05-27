from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


EnvironmentPolicyStatus = Literal["PASS", "WARN", "FAIL"]


class EnvironmentPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/security")

    environment: str = "development"
    allow_live: bool = False
    require_dry_run: bool = True
    require_production_guard: bool = True
    require_kill_switch: bool = True
    forbid_debug_in_production: bool = True
    forbid_env_secrets_in_production: bool = True


class EnvironmentPolicyInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    environment: str = "development"
    execution_mode: str = "paper"
    debug: bool = False

    dry_run: bool = True
    production_guard_enabled: bool = True
    kill_switch_enabled: bool = True

    live_order_adapter_enabled: bool = False
    live_order_submission_allowed: bool = False

    secrets_storage_backend: str = "env"
    api_keys_present: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)


class EnvironmentPolicyFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: EnvironmentPolicyStatus
    message: str
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class EnvironmentPolicyReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "environment_policy_guard"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: EnvironmentPolicyStatus

    findings_count: int
    blocking_findings_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    findings: list[dict[str, Any]] = Field(default_factory=list)
    inputs: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_environment_policy_config() -> EnvironmentPolicyConfig:
    return EnvironmentPolicyConfig(
        output_dir=Path(os.getenv("ENV_POLICY_OUTPUT_DIR", "artifacts/security")),
        environment=os.getenv("ENV_POLICY_ENVIRONMENT", "development"),
        allow_live=env_bool("ENV_POLICY_ALLOW_LIVE", False),
        require_dry_run=env_bool("ENV_POLICY_REQUIRE_DRY_RUN", True),
        require_production_guard=env_bool("ENV_POLICY_REQUIRE_PRODUCTION_GUARD", True),
        require_kill_switch=env_bool("ENV_POLICY_REQUIRE_KILL_SWITCH", True),
        forbid_debug_in_production=env_bool("ENV_POLICY_FORBID_DEBUG_IN_PRODUCTION", True),
        forbid_env_secrets_in_production=env_bool("ENV_POLICY_FORBID_ENV_SECRETS_IN_PRODUCTION", True),
    )


def environment_policy_inputs_from_env() -> EnvironmentPolicyInputs:
    return EnvironmentPolicyInputs(
        environment=os.getenv("ENV_POLICY_ENVIRONMENT", os.getenv("PRODUCTION_ENVIRONMENT", "development")),
        execution_mode=os.getenv("BINANCE_EXECUTION_MODE", "paper"),
        debug=env_bool("DEBUG", False),
        dry_run=env_bool("LIVE_ORDER_ADAPTER_DRY_RUN", True),
        production_guard_enabled=env_bool("PRODUCTION_GUARD_ENABLED", True),
        kill_switch_enabled=env_bool("KILL_SWITCH_ENABLED", True),
        live_order_adapter_enabled=env_bool("LIVE_ORDER_ADAPTER_ENABLED", False),
        live_order_submission_allowed=env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
        secrets_storage_backend=os.getenv("SECRETS_STORAGE_BACKEND", "env"),
        api_keys_present=bool(os.getenv("BINANCE_API_KEY")) or bool(os.getenv("BINANCE_API_SECRET")),
    )


def policy_finding(
    *,
    code: str,
    ok: bool,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = True,
) -> EnvironmentPolicyFinding:
    return EnvironmentPolicyFinding(
        code=code if ok else f"{code}_FAILED",
        status="PASS" if ok else "FAIL",
        message=message,
        value=value,
        expected=expected,
        blocking=not ok and blocking,
    )


def warning(
    *,
    code: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
) -> EnvironmentPolicyFinding:
    return EnvironmentPolicyFinding(
        code=code,
        status="WARN",
        message=message,
        value=value,
        expected=expected,
        blocking=False,
    )


def evaluate_environment_policy(
    *,
    inputs: EnvironmentPolicyInputs | dict[str, Any] | None = None,
    config: EnvironmentPolicyConfig | None = None,
) -> EnvironmentPolicyReport:
    resolved_config = config or load_environment_policy_config()
    resolved_inputs = (
        environment_policy_inputs_from_env()
        if inputs is None
        else inputs if isinstance(inputs, EnvironmentPolicyInputs)
        else EnvironmentPolicyInputs.model_validate(inputs)
    )

    findings: list[EnvironmentPolicyFinding] = []

    live_intent = (
        resolved_inputs.execution_mode == "live"
        or resolved_inputs.live_order_adapter_enabled
        or resolved_inputs.live_order_submission_allowed
    )

    if live_intent and not resolved_config.allow_live:
        findings.append(
            policy_finding(
                code="LIVE_NOT_ALLOWED",
                ok=False,
                message="Live intent detectado, mas política não permite live.",
                value=True,
                expected=False,
            )
        )

    if resolved_config.require_dry_run:
        findings.append(
            policy_finding(
                code="DRY_RUN_REQUIRED",
                ok=resolved_inputs.dry_run,
                message="dry_run precisa estar ativo.",
                value=resolved_inputs.dry_run,
                expected=True,
            )
        )

    if resolved_config.require_production_guard:
        findings.append(
            policy_finding(
                code="PRODUCTION_GUARD_REQUIRED",
                ok=resolved_inputs.production_guard_enabled,
                message="Production guard precisa estar ativo.",
                value=resolved_inputs.production_guard_enabled,
                expected=True,
            )
        )

    if resolved_config.require_kill_switch:
        findings.append(
            policy_finding(
                code="KILL_SWITCH_REQUIRED",
                ok=resolved_inputs.kill_switch_enabled,
                message="Kill switch precisa estar ativo.",
                value=resolved_inputs.kill_switch_enabled,
                expected=True,
            )
        )

    if resolved_config.forbid_debug_in_production and resolved_inputs.environment == "production":
        findings.append(
            policy_finding(
                code="DEBUG_FORBIDDEN_IN_PRODUCTION",
                ok=not resolved_inputs.debug,
                message="Debug proibido em produção.",
                value=resolved_inputs.debug,
                expected=False,
            )
        )

    if (
        resolved_config.forbid_env_secrets_in_production
        and resolved_inputs.environment == "production"
        and resolved_inputs.api_keys_present
        and resolved_inputs.secrets_storage_backend == "env"
    ):
        findings.append(
            policy_finding(
                code="ENV_SECRETS_FORBIDDEN_IN_PRODUCTION",
                ok=False,
                message="Secrets em env são proibidos em produção madura; usar vault/secrets manager.",
                value=resolved_inputs.secrets_storage_backend,
                expected="vault",
            )
        )

    if not resolved_inputs.api_keys_present:
        findings.append(
            warning(
                code="API_KEYS_NOT_PRESENT",
                message="API keys ausentes. Isso é esperado em dev/paper, mas live não poderá ativar.",
                value=False,
                expected=True,
            )
        )

    blockers = [item.code for item in findings if item.blocking]
    warnings = [item.code for item in findings if item.status == "WARN"]
    passed = not blockers

    return EnvironmentPolicyReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        findings_count=len(findings),
        blocking_findings_count=len(blockers),
        blockers=blockers,
        warnings=warnings,
        findings=[item.model_dump(mode="json") for item in findings],
        inputs=resolved_inputs.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_environment_policy_report(
    report: EnvironmentPolicyReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "environment_policy_latest",
) -> Path:
    config = load_environment_policy_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path