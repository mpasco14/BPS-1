from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()

__test__ = False


CredentialStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetCredentialReadinessConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_supervision")

    rest_base_url: str = "https://demo-fapi.binance.com"
    ws_base_url: str = "wss://fstream.binancefuture.com"

    require_api_keys: bool = False
    require_testnet_endpoint: bool = True
    block_if_live_flags: bool = True


class TestnetCredentialReadinessReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_credential_endpoint_readiness"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: CredentialStatus
    passed: bool

    api_key_present: bool
    api_secret_present: bool

    execution_mode: str
    rest_base_url: str
    ws_base_url: str

    testnet_endpoint_detected: bool
    live_flags_detected: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def has_env_value(*names: str) -> bool:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return True

    return False


def load_testnet_credential_readiness_config() -> TestnetCredentialReadinessConfig:
    return TestnetCredentialReadinessConfig(
        output_dir=Path(os.getenv("TESTNET_CREDENTIAL_READINESS_OUTPUT_DIR", "artifacts/testnet_supervision")),
        rest_base_url=os.getenv("TESTNET_REST_BASE_URL", "https://demo-fapi.binance.com"),
        ws_base_url=os.getenv("TESTNET_WS_BASE_URL", "wss://fstream.binancefuture.com"),
        require_api_keys=env_bool("TESTNET_REQUIRE_API_KEYS", False),
        require_testnet_endpoint=env_bool("TESTNET_REQUIRE_TESTNET_ENDPOINT", True),
        block_if_live_flags=env_bool("TESTNET_BLOCK_IF_LIVE_FLAGS", True),
    )


def endpoint_looks_testnet(rest_base_url: str, ws_base_url: str) -> bool:
    combined = f"{rest_base_url} {ws_base_url}".lower()

    return (
        "demo-fapi" in combined
        or "testnet" in combined
        or "fstream.binancefuture.com" in combined
    )


def live_flags_are_active() -> bool:
    return any(
        [
            env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
            env_bool("RISK_ALLOW_LIVE_TRADING", False),
            env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
        ]
    )


def evaluate_testnet_credential_readiness(
    *,
    config: TestnetCredentialReadinessConfig | None = None,
    metadata: dict[str, Any] | None = None,
) -> TestnetCredentialReadinessReport:
    resolved_config = config or load_testnet_credential_readiness_config()

    api_key_present = has_env_value(
        "BINANCE_TESTNET_API_KEY",
        "BINANCE_API_KEY_TESTNET",
        "BINANCE_API_KEY",
    )
    api_secret_present = has_env_value(
        "BINANCE_TESTNET_API_SECRET",
        "BINANCE_API_SECRET_TESTNET",
        "BINANCE_API_SECRET",
    )

    execution_mode = os.getenv("BINANCE_EXECUTION_MODE", "testnet").strip().lower()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    testnet_endpoint_detected = endpoint_looks_testnet(
        resolved_config.rest_base_url,
        resolved_config.ws_base_url,
    )

    live_flags_detected = live_flags_are_active()

    if execution_mode not in {"testnet", "paper"}:
        blockers.append("execution_mode_not_testnet_or_paper")

    if resolved_config.require_api_keys and not api_key_present:
        blockers.append("testnet_api_key_missing")

    if resolved_config.require_api_keys and not api_secret_present:
        blockers.append("testnet_api_secret_missing")

    if not api_key_present or not api_secret_present:
        warnings.append("testnet_api_credentials_not_fully_configured")
        recommendations.append("Para sessão testnet real, configurar API key/secret de testnet.")

    if resolved_config.require_testnet_endpoint and not testnet_endpoint_detected:
        blockers.append("testnet_endpoint_not_detected")

    if resolved_config.block_if_live_flags and live_flags_detected:
        blockers.append("live_flags_detected_during_testnet_readiness")

    if resolved_config.rest_base_url.startswith("https://fapi.binance.com"):
        blockers.append("live_rest_endpoint_detected")

    if resolved_config.ws_base_url.startswith("wss://fstream.binance.com"):
        blockers.append("live_ws_endpoint_detected")

    recommendations.append("Manter live trading desabilitado durante validação testnet supervisionada.")

    passed = not blockers

    return TestnetCredentialReadinessReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        api_key_present=api_key_present,
        api_secret_present=api_secret_present,
        execution_mode=execution_mode,
        rest_base_url=resolved_config.rest_base_url,
        ws_base_url=resolved_config.ws_base_url,
        testnet_endpoint_detected=testnet_endpoint_detected,
        live_flags_detected=live_flags_detected,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        config={
            **resolved_config.model_dump(mode="json"),
            "metadata": metadata or {},
        },
    )


def export_testnet_credential_readiness_report(
    report: TestnetCredentialReadinessReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_credential_readiness_report",
) -> Path:
    config = load_testnet_credential_readiness_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path