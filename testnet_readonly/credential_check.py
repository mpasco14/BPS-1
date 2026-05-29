from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.signed_client import (
    BinanceTestnetAdapterConfig,
    endpoint_is_testnet,
    load_binance_testnet_adapter_config,
)


load_dotenv()

__test__ = False


ReadOnlyCredentialStatus = Literal["PASS", "WARN", "FAIL"]


class RealTestnetCredentialCheckConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_readonly")
    require_real_mode: bool = False
    require_no_live_flags: bool = True


class RealTestnetCredentialCheckReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "real_testnet_readonly_credential_check"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ReadOnlyCredentialStatus
    passed: bool

    execution_mode: str
    adapter_simulate: bool

    api_key_present: bool
    api_secret_present: bool

    rest_base_url: str
    testnet_endpoint: bool

    live_flags_detected: bool
    order_submission_allowed: bool
    cancel_orders_allowed: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    adapter_config: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_real_testnet_credential_check_config() -> RealTestnetCredentialCheckConfig:
    return RealTestnetCredentialCheckConfig(
        output_dir=Path(os.getenv("TESTNET_READONLY_CREDENTIAL_OUTPUT_DIR", "artifacts/testnet_readonly")),
        require_real_mode=env_bool("TESTNET_READONLY_REQUIRE_REAL_MODE", False),
        require_no_live_flags=env_bool("TESTNET_READONLY_REQUIRE_NO_LIVE_FLAGS", True),
    )


def readonly_live_flags_detected() -> bool:
    return any(
        [
            env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
            env_bool("RISK_ALLOW_LIVE_TRADING", False),
            env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
        ]
    )


def evaluate_real_testnet_credential_check(
    *,
    adapter_config: BinanceTestnetAdapterConfig | None = None,
    config: RealTestnetCredentialCheckConfig | None = None,
) -> RealTestnetCredentialCheckReport:
    resolved_adapter = adapter_config or load_binance_testnet_adapter_config()
    resolved_config = config or load_real_testnet_credential_check_config()

    execution_mode = os.getenv("BINANCE_EXECUTION_MODE", "testnet").strip().lower()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    api_key_present = bool(resolved_adapter.api_key)
    api_secret_present = bool(resolved_adapter.api_secret)
    testnet_endpoint = endpoint_is_testnet(resolved_adapter.rest_base_url)
    live_flags = readonly_live_flags_detected()

    if execution_mode != "testnet":
        blockers.append("execution_mode_must_be_testnet")

    if not testnet_endpoint:
        blockers.append("testnet_endpoint_not_detected")

    if resolved_config.require_real_mode and resolved_adapter.simulate:
        blockers.append("real_mode_required_but_adapter_is_simulated")

    if not resolved_adapter.simulate and not api_key_present:
        blockers.append("api_key_required_for_real_readonly")

    if not resolved_adapter.simulate and not api_secret_present:
        blockers.append("api_secret_required_for_real_readonly")

    if resolved_adapter.simulate:
        warnings.append("adapter_is_simulated")
        recommendations.append("Para leitura real, definir BINANCE_TESTNET_SIMULATE=false com credenciais de testnet.")

    if resolved_config.require_no_live_flags and live_flags:
        blockers.append("live_flags_detected_in_readonly_validation")

    if resolved_adapter.allow_order_submission:
        blockers.append("order_submission_must_be_disabled_for_readonly_validation")

    if resolved_adapter.allow_cancel_orders:
        blockers.append("cancel_orders_must_be_disabled_for_readonly_validation")

    recommendations.append("Manter ordem e cancelamento desabilitados durante validação read-only.")
    recommendations.append("Nunca commitar .env com API key/secret.")

    passed = not blockers

    return RealTestnetCredentialCheckReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        execution_mode=execution_mode,
        adapter_simulate=resolved_adapter.simulate,
        api_key_present=api_key_present,
        api_secret_present=api_secret_present,
        rest_base_url=resolved_adapter.rest_base_url,
        testnet_endpoint=testnet_endpoint,
        live_flags_detected=live_flags,
        order_submission_allowed=resolved_adapter.allow_order_submission,
        cancel_orders_allowed=resolved_adapter.allow_cancel_orders,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        adapter_config=resolved_adapter.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def export_real_testnet_credential_check_report(
    report: RealTestnetCredentialCheckReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_credential_check",
) -> Path:
    config = load_real_testnet_credential_check_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path