"""
Binance Futures testnet client helpers.

Responsabilidades:
- Centralizar configuração de testnet.
- Validar se credenciais de testnet existem.
- Criar payload de health/connection readiness.
- Não submeter ordens por padrão.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


class BinanceTestnetConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    base_url: str = "https://testnet.binancefuture.com"
    fstream_ws_url: str = "wss://stream.binancefuture.com"

    api_key: str | None = None
    api_secret: str | None = None

    connection_timeout_seconds: int = 10
    allow_order_submission: bool = False


class BinanceTestnetReadiness(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_testnet_client"
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    ready: bool
    status: str

    enabled: bool
    has_api_key: bool
    has_api_secret: bool
    allow_order_submission: bool

    blockers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_binance_testnet_config() -> BinanceTestnetConfig:
    return BinanceTestnetConfig(
        enabled=env_bool("BINANCE_TESTNET_ENABLED", True),
        base_url=os.getenv(
            "BINANCE_TESTNET_BASE_URL",
            "https://testnet.binancefuture.com",
        ),
        fstream_ws_url=os.getenv(
            "BINANCE_TESTNET_FSTREAM_WS_URL",
            "wss://stream.binancefuture.com",
        ),
        api_key=os.getenv("BINANCE_TESTNET_API_KEY") or None,
        api_secret=os.getenv("BINANCE_TESTNET_API_SECRET") or None,
        connection_timeout_seconds=env_int(
            "BINANCE_TESTNET_CONNECTION_TIMEOUT_SECONDS",
            10,
        ),
        allow_order_submission=env_bool(
            "BINANCE_TESTNET_ALLOW_ORDER_SUBMISSION",
            False,
        ),
    )


def evaluate_binance_testnet_readiness(
    config: BinanceTestnetConfig | None = None,
) -> BinanceTestnetReadiness:
    resolved = config or load_binance_testnet_config()

    blockers: list[str] = []

    if not resolved.enabled:
        blockers.append("testnet_disabled")

    if not resolved.api_key:
        blockers.append("testnet_api_key_missing")

    if not resolved.api_secret:
        blockers.append("testnet_api_secret_missing")

    ready = len(blockers) == 0

    return BinanceTestnetReadiness(
        ready=ready,
        status="PASS" if ready else "FAIL",
        enabled=resolved.enabled,
        has_api_key=bool(resolved.api_key),
        has_api_secret=bool(resolved.api_secret),
        allow_order_submission=resolved.allow_order_submission,
        blockers=blockers,
        metadata={
            "base_url": resolved.base_url,
            "fstream_ws_url": resolved.fstream_ws_url,
            "connection_timeout_seconds": resolved.connection_timeout_seconds,
        },
    )


def assert_testnet_order_submission_allowed(
    config: BinanceTestnetConfig | None = None,
) -> None:
    resolved = config or load_binance_testnet_config()

    if not resolved.allow_order_submission:
        raise PermissionError("BINANCE_TESTNET_ALLOW_ORDER_SUBMISSION=false")

    readiness = evaluate_binance_testnet_readiness(resolved)

    if not readiness.ready:
        raise PermissionError(f"testnet_not_ready:{readiness.blockers}")