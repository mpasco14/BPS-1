from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.api_error import BinanceAPIErrorClassification, classify_binance_api_error


load_dotenv()

__test__ = False


ClientResponseStatus = Literal["OK", "SIMULATED", "ERROR", "BLOCKED"]


class BinanceTestnetAdapterConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/binance_testnet_adapter")

    rest_base_url: str = "https://demo-fapi.binance.com"
    recv_window: int = 5000
    timeout_seconds: int = 10

    api_key: str | None = None
    api_secret: str | None = None

    simulate: bool = True
    require_testnet_endpoint: bool = True
    allow_order_submission: bool = False
    allow_cancel_orders: bool = False

    max_retries: int = 2
    backoff_seconds: int = 1


class BinanceSignedRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    method: str
    path: str
    params: dict[str, Any] = Field(default_factory=dict)
    signed: bool = True


class BinanceSignedResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_testnet_signed_client"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ClientResponseStatus
    ok: bool

    method: str
    path: str
    url: str | None = None

    http_status: int | None = None
    data: Any = None
    headers: dict[str, Any] = Field(default_factory=dict)

    error_code: int | None = None
    error_message: str | None = None
    error_classification: dict[str, Any] | None = None

    simulated: bool = False
    blocked_reason: str | None = None


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


def load_binance_testnet_adapter_config() -> BinanceTestnetAdapterConfig:
    return BinanceTestnetAdapterConfig(
        output_dir=Path(os.getenv("BINANCE_TESTNET_ADAPTER_OUTPUT_DIR", "artifacts/binance_testnet_adapter")),
        rest_base_url=os.getenv("BINANCE_TESTNET_REST_BASE_URL", "https://demo-fapi.binance.com"),
        recv_window=env_int("BINANCE_TESTNET_RECV_WINDOW", 5000),
        timeout_seconds=env_int("BINANCE_TESTNET_REQUEST_TIMEOUT_SECONDS", 10),
        api_key=os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY_TESTNET"),
        api_secret=os.getenv("BINANCE_TESTNET_API_SECRET") or os.getenv("BINANCE_API_SECRET_TESTNET"),
        simulate=env_bool("BINANCE_TESTNET_SIMULATE", True),
        require_testnet_endpoint=env_bool("BINANCE_TESTNET_REQUIRE_TESTNET_ENDPOINT", True),
        allow_order_submission=env_bool("BINANCE_TESTNET_ALLOW_ORDER_SUBMISSION", False),
        allow_cancel_orders=env_bool("BINANCE_TESTNET_ALLOW_CANCEL_ORDERS", False),
        max_retries=env_int("BINANCE_TESTNET_MAX_RETRIES", 2),
        backoff_seconds=env_int("BINANCE_TESTNET_BACKOFF_SECONDS", 1),
    )


def endpoint_is_testnet(base_url: str) -> bool:
    normalized = base_url.strip().lower()

    return "demo-fapi" in normalized or "testnet" in normalized


def build_query_string(params: dict[str, Any]) -> str:
    clean_params = {
        key: value
        for key, value in params.items()
        if value is not None
    }

    return urllib.parse.urlencode(clean_params, doseq=True)


def sign_query_string(query_string: str, api_secret: str) -> str:
    return hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class BinanceTestnetSignedClient:
    def __init__(self, config: BinanceTestnetAdapterConfig | None = None) -> None:
        self.config = config or load_binance_testnet_adapter_config()

    def build_signed_params(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved_params = dict(params or {})
        resolved_params.setdefault("recvWindow", self.config.recv_window)
        resolved_params["timestamp"] = int(time.time() * 1000)

        query_string = build_query_string(resolved_params)
        signature = sign_query_string(query_string, self.config.api_secret or "")

        return {
            **resolved_params,
            "signature": signature,
        }

    def validate_request_safety(self, *, signed: bool = True) -> str | None:
        if self.config.require_testnet_endpoint and not endpoint_is_testnet(self.config.rest_base_url):
            return "non_testnet_endpoint_blocked"

        if signed and not self.config.api_key:
            return "api_key_missing"

        if signed and not self.config.api_secret:
            return "api_secret_missing"

        return None

    def request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = True,
        simulate_data: Any = None,
    ) -> BinanceSignedResponse:
        normalized_method = method.upper()
        normalized_path = path if path.startswith("/") else f"/{path}"

        if self.config.simulate:
            return BinanceSignedResponse(
                status="SIMULATED",
                ok=True,
                method=normalized_method,
                path=normalized_path,
                url=f"{self.config.rest_base_url}{normalized_path}",
                data=simulate_data if simulate_data is not None else {"simulated": True},
                simulated=True,
            )

        blocked_reason = self.validate_request_safety(signed=signed)

        if blocked_reason:
            return BinanceSignedResponse(
                status="BLOCKED",
                ok=False,
                method=normalized_method,
                path=normalized_path,
                url=f"{self.config.rest_base_url}{normalized_path}",
                blocked_reason=blocked_reason,
            )

        final_params = self.build_signed_params(params) if signed else dict(params or {})
        query_string = build_query_string(final_params)
        url = f"{self.config.rest_base_url}{normalized_path}"

        if query_string:
            url = f"{url}?{query_string}"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        if signed:
            headers["X-MBX-APIKEY"] = self.config.api_key or ""

        request = urllib.request.Request(
            url=url,
            data=None,
            headers=headers,
            method=normalized_method,
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                payload = json.loads(body) if body else {}

                return BinanceSignedResponse(
                    status="OK",
                    ok=True,
                    method=normalized_method,
                    path=normalized_path,
                    url=url,
                    http_status=response.status,
                    data=payload,
                    headers=dict(response.headers),
                    simulated=False,
                )

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")

            error_code = None
            error_message = body

            try:
                payload = json.loads(body)
                error_code = payload.get("code")
                error_message = payload.get("msg", body)
            except json.JSONDecodeError:
                payload = {"raw": body}

            classification = classify_binance_api_error(
                http_status=exc.code,
                error_code=error_code,
                message=error_message,
                metadata={"path": normalized_path, "method": normalized_method},
            )

            return BinanceSignedResponse(
                status="ERROR",
                ok=False,
                method=normalized_method,
                path=normalized_path,
                url=url,
                http_status=exc.code,
                data=payload,
                headers=dict(exc.headers),
                error_code=error_code,
                error_message=error_message,
                error_classification=classification.model_dump(mode="json"),
            )

        except OSError as exc:
            classification = classify_binance_api_error(
                message=str(exc),
                metadata={"path": normalized_path, "method": normalized_method},
            )

            return BinanceSignedResponse(
                status="ERROR",
                ok=False,
                method=normalized_method,
                path=normalized_path,
                url=url,
                error_message=str(exc),
                error_classification=classification.model_dump(mode="json"),
            )


def build_binance_testnet_signed_client(
    config: BinanceTestnetAdapterConfig | None = None,
) -> BinanceTestnetSignedClient:
    return BinanceTestnetSignedClient(config=config)