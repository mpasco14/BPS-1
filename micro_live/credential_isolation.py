from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live.common import env_bool, env_str, export_json, live_order_flags_detected


CredentialIsolationStatus = Literal["PASS", "WARN", "FAIL"]


class LiveCredentialIsolationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/micro_live")

    require_live_keys: bool = False
    require_key_isolation: bool = True
    require_no_testnet_keys_in_live: bool = True
    require_no_live_order_flags: bool = True

    live_api_key: str = ""
    live_api_secret: str = ""
    testnet_api_key: str = ""
    testnet_api_secret: str = ""


class LiveCredentialIsolationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_live_credential_isolation"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: CredentialIsolationStatus
    passed: bool

    live_key_present: bool
    live_secret_present: bool
    testnet_key_present: bool
    testnet_secret_present: bool

    key_isolated: bool
    live_order_flags_detected: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    config: dict[str, Any]


def load_live_credential_isolation_config() -> LiveCredentialIsolationConfig:
    return LiveCredentialIsolationConfig(
        output_dir=Path(os.getenv("MICRO_LIVE_OUTPUT_DIR", "artifacts/micro_live")),
        require_live_keys=env_bool("MICRO_LIVE_REQUIRE_LIVE_KEYS", False),
        require_key_isolation=env_bool("MICRO_LIVE_REQUIRE_KEY_ISOLATION", True),
        require_no_testnet_keys_in_live=env_bool("MICRO_LIVE_REQUIRE_NO_TESTNET_KEYS_IN_LIVE", True),
        require_no_live_order_flags=env_bool("MICRO_LIVE_REQUIRE_NO_LIVE_ORDER_FLAGS", True),
        live_api_key=env_str("MICRO_LIVE_LIVE_API_KEY"),
        live_api_secret=env_str("MICRO_LIVE_LIVE_API_SECRET"),
        testnet_api_key=env_str("MICRO_LIVE_TESTNET_API_KEY") or env_str("BINANCE_TESTNET_API_KEY"),
        testnet_api_secret=env_str("MICRO_LIVE_TESTNET_API_SECRET") or env_str("BINANCE_TESTNET_API_SECRET"),
    )


def evaluate_live_credential_isolation(
    *,
    config: LiveCredentialIsolationConfig | None = None,
) -> LiveCredentialIsolationReport:
    resolved = config or load_live_credential_isolation_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    live_key_present = bool(resolved.live_api_key)
    live_secret_present = bool(resolved.live_api_secret)
    testnet_key_present = bool(resolved.testnet_api_key)
    testnet_secret_present = bool(resolved.testnet_api_secret)

    key_isolated = True

    if resolved.live_api_key and resolved.testnet_api_key:
        if resolved.live_api_key == resolved.testnet_api_key:
            key_isolated = False

    if resolved.live_api_secret and resolved.testnet_api_secret:
        if resolved.live_api_secret == resolved.testnet_api_secret:
            key_isolated = False

    live_flags = live_order_flags_detected()

    if resolved.require_live_keys and not live_key_present:
        blockers.append("live_api_key_missing")

    if resolved.require_live_keys and not live_secret_present:
        blockers.append("live_api_secret_missing")

    if resolved.require_key_isolation and not key_isolated:
        blockers.append("live_and_testnet_keys_not_isolated")

    if resolved.require_no_testnet_keys_in_live and resolved.live_api_key and resolved.live_api_key == resolved.testnet_api_key:
        blockers.append("testnet_key_reused_as_live_key")

    if resolved.require_no_live_order_flags and live_flags:
        blockers.append("live_order_flags_enabled_before_go_no_go")

    if not live_key_present or not live_secret_present:
        warnings.append("live_credentials_not_configured")
        recommendations.append("Configurar credenciais live somente quando for abrir micro-live supervisionado.")

    recommendations.append("Nunca commitar .env com chaves reais.")
    recommendations.append("Usar chaves live separadas das chaves testnet.")
    recommendations.append("Manter flags de envio live desligadas até o relatório GO.")

    passed = not blockers

    return LiveCredentialIsolationReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        live_key_present=live_key_present,
        live_secret_present=live_secret_present,
        testnet_key_present=testnet_key_present,
        testnet_secret_present=testnet_secret_present,
        key_isolated=key_isolated,
        live_order_flags_detected=live_flags,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        config={
            **resolved.model_dump(mode="json"),
            "live_api_key": "***" if resolved.live_api_key else "",
            "live_api_secret": "***" if resolved.live_api_secret else "",
            "testnet_api_key": "***" if resolved.testnet_api_key else "",
            "testnet_api_secret": "***" if resolved.testnet_api_secret else "",
        },
    )


def export_live_credential_isolation_report(
    report: LiveCredentialIsolationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "micro_live_credential_isolation",
) -> Path:
    resolved = load_live_credential_isolation_config()
    return export_json(report, output_dir=output_dir or resolved.output_dir, name=name)