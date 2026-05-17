"""
Binance Futures REST client.

Responsabilidades:
- Assinar requests privadas com HMAC SHA256.
- Separar paper/testnet/live.
- Expor wrappers seguros para test order, live order e cancelamento.
- Nunca permitir live trading sem BINANCE_ALLOW_LIVE_TRADING=true.

Este módulo NÃO decide trades.
Este módulo NÃO faz sizing.
Este módulo NÃO ignora risk_manager.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ExecutionMode = Literal["paper", "testnet", "live"]


class BinanceFuturesConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_key: str = ""
    api_secret: str = ""

    execution_mode: ExecutionMode = "paper"
    allow_live_trading: bool = False

    rest_base_url: str = "https://fapi.binance.com"
    testnet_rest_base_url: str = "https://demo-fapi.binance.com"

    recv_window: int = 5000
    timeout_seconds: float = 15.0

    @property
    def active_base_url(self) -> str:
        if self.execution_mode == "testnet":
            return self.testnet_rest_base_url.rstrip("/")

        return self.rest_base_url.rstrip("/")

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_binance_futures_config() -> BinanceFuturesConfig:
    mode = os.getenv("BINANCE_EXECUTION_MODE", "paper").strip().lower()

    if mode not in {"paper", "testnet", "live"}:
        mode = "paper"

    return BinanceFuturesConfig(
        api_key=os.getenv("BINANCE_FUTURES_API_KEY", ""),
        api_secret=os.getenv("BINANCE_FUTURES_API_SECRET", ""),
        execution_mode=mode,  # type: ignore[arg-type]
        allow_live_trading=env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
        rest_base_url=os.getenv("BINANCE_FUTURES_REST_BASE_URL", "https://fapi.binance.com"),
        testnet_rest_base_url=os.getenv("BINANCE_FUTURES_TESTNET_REST_BASE_URL", "https://demo-fapi.binance.com"),
        recv_window=int(os.getenv("BINANCE_FUTURES_RECV_WINDOW", "5000")),
        timeout_seconds=float(os.getenv("BINANCE_FUTURES_REQUEST_TIMEOUT_SECONDS", "15")),
    )


def current_timestamp_ms() -> int:
    return int(time.time() * 1000)


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return ""

    if len(value) <= visible:
        return "*" * len(value)

    return f"{value[:visible]}{'*' * (len(value) - visible)}"


def clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in params.items()
        if value is not None
    }


def sign_query(params: dict[str, Any], secret: str) -> str:
    query_string = urlencode(clean_params(params), doseq=True)

    return hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_signed_params(
    params: dict[str, Any],
    *,
    secret: str,
    timestamp: int | None = None,
    recv_window: int | None = None,
) -> dict[str, Any]:
    signed = dict(clean_params(params))
    signed["timestamp"] = timestamp if timestamp is not None else current_timestamp_ms()

    if recv_window is not None:
        signed["recvWindow"] = recv_window

    signed["signature"] = sign_query(signed, secret)

    return signed


class BinanceFuturesRestClient:
    def __init__(self, config: BinanceFuturesConfig | None = None) -> None:
        self.config = config or load_binance_futures_config()
        self.client = httpx.Client(timeout=self.config.timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def headers(self) -> dict[str, str]:
        if not self.config.api_key:
            return {}

        return {"X-MBX-APIKEY": self.config.api_key}

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any] | list[Any]:
        request_params = params or {}

        if signed:
            if not self.config.has_credentials:
                raise RuntimeError("Credenciais Binance Futures ausentes.")

            request_params = build_signed_params(
                request_params,
                secret=self.config.api_secret,
                recv_window=self.config.recv_window,
            )

        url = f"{self.config.active_base_url}{path}"

        response = self.client.request(
            method.upper(),
            url,
            params=request_params,
            headers=self.headers(),
        )
        response.raise_for_status()

        if not response.text:
            return {}

        return response.json()

    def get_exchange_info(self) -> dict[str, Any]:
        result = self.request("GET", "/fapi/v1/exchangeInfo")

        if not isinstance(result, dict):
            raise RuntimeError("Resposta inesperada de exchangeInfo.")

        return result

    def new_order_test(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.config.execution_mode == "paper":
            return {
                "paper": True,
                "endpoint": "/fapi/v1/order/test",
                "params": params,
            }

        result = self.request(
            "POST",
            "/fapi/v1/order/test",
            params=params,
            signed=True,
        )

        return result if isinstance(result, dict) else {"result": result}

    def new_order(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.config.execution_mode == "paper":
            return {
                "paper": True,
                "endpoint": "/fapi/v1/order",
                "params": params,
            }

        if self.config.execution_mode == "live" and not self.config.allow_live_trading:
            raise RuntimeError("Live trading bloqueado. Configure BINANCE_ALLOW_LIVE_TRADING=true explicitamente.")

        result = self.request(
            "POST",
            "/fapi/v1/order",
            params=params,
            signed=True,
        )

        return result if isinstance(result, dict) else {"result": result}

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: int | None = None,
        orig_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        if order_id is None and orig_client_order_id is None:
            raise ValueError("Informe order_id ou orig_client_order_id.")

        params = {
            "symbol": symbol.upper(),
            "orderId": order_id,
            "origClientOrderId": orig_client_order_id,
        }

        if self.config.execution_mode == "paper":
            return {
                "paper": True,
                "endpoint": "/fapi/v1/order",
                "params": clean_params(params),
                "status": "CANCELED",
            }

        result = self.request(
            "DELETE",
            "/fapi/v1/order",
            params=params,
            signed=True,
        )

        return result if isinstance(result, dict) else {"result": result}

    def get_open_orders(self, symbol: str | None = None) -> dict[str, Any] | list[Any]:
        params = {"symbol": symbol.upper()} if symbol else {}

        return self.request(
            "GET",
            "/fapi/v1/openOrders",
            params=params,
            signed=True,
        )

    def create_listen_key(self) -> str:
        result = self.request(
            "POST",
            "/fapi/v1/listenKey",
            signed=False,
        )

        if not isinstance(result, dict) or "listenKey" not in result:
            raise RuntimeError("Não foi possível criar listenKey.")

        return str(result["listenKey"])

    def keepalive_listen_key(self, listen_key: str) -> dict[str, Any]:
        result = self.request(
            "PUT",
            "/fapi/v1/listenKey",
            params={"listenKey": listen_key},
            signed=False,
        )

        return result if isinstance(result, dict) else {"result": result}

    def close_listen_key(self, listen_key: str) -> dict[str, Any]:
        result = self.request(
            "DELETE",
            "/fapi/v1/listenKey",
            params={"listenKey": listen_key},
            signed=False,
        )

        return result if isinstance(result, dict) else {"result": result}