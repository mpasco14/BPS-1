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

from execution.binance_testnet_client import (
    BinanceTestnetConfig,
    assert_testnet_order_submission_allowed,
    evaluate_binance_testnet_readiness,
    load_binance_testnet_config,
)


load_dotenv()


TestnetOrderAction = Literal["CREATE", "QUERY", "CANCEL", "TEST"]
TestnetOrderLifecycleStatus = Literal["DRY_RUN", "SUBMITTED", "QUERIED", "CANCELLED", "FAILED"]


class BinanceTestnetOrderRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    side: Literal["BUY", "SELL"]
    type: str = "LIMIT"
    timeInForce: str = "GTC"

    quantity: str
    price: str | None = None

    newClientOrderId: str | None = None
    reduceOnly: bool | None = None
    recvWindow: int | None = None


class BinanceTestnetOrderResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_testnet_orders"
    action: TestnetOrderAction
    status: TestnetOrderLifecycleStatus

    symbol: str
    order_id: str | int | None = None
    client_order_id: str | None = None
    order_status: str | None = None

    dry_run: bool = True
    latency_ms: float | None = None

    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def now_ms() -> int:
    return int(time.time() * 1000)


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


def sign_query_string(query_string: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_signed_params(
    params: dict[str, Any],
    *,
    api_secret: str,
) -> dict[str, Any]:
    cleaned = {
        key: value
        for key, value in params.items()
        if value is not None
    }

    cleaned.setdefault("timestamp", now_ms())

    query_string = urllib.parse.urlencode(cleaned, doseq=True)
    signature = sign_query_string(query_string, api_secret)

    return {
        **cleaned,
        "signature": signature,
    }


def build_order_params(request: BinanceTestnetOrderRequest) -> dict[str, Any]:
    params = request.model_dump(mode="json", exclude_none=True)

    if params.get("reduceOnly") is not None:
        params["reduceOnly"] = "true" if params["reduceOnly"] else "false"

    if params.get("recvWindow") is None:
        recv_window = env_int("TESTNET_ORDER_LIFECYCLE_RECV_WINDOW", 5000)
        params["recvWindow"] = recv_window

    return params


class BinanceTestnetOrdersClient:
    def __init__(self, config: BinanceTestnetConfig | None = None):
        self.config = config or load_binance_testnet_config()

    def _signed_request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.config.api_key:
            raise PermissionError("testnet_api_key_missing")

        if not self.config.api_secret:
            raise PermissionError("testnet_api_secret_missing")

        signed = build_signed_params(
            params,
            api_secret=self.config.api_secret,
        )

        query = urllib.parse.urlencode(signed, doseq=True)
        url = f"{self.config.base_url}{path}?{query}"

        request = urllib.request.Request(
            url=url,
            method=method,
            headers={
                "X-MBX-APIKEY": self.config.api_key,
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.connection_timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8")

                if not raw:
                    return {}

                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"binance_http_error:{exc.code}:{raw_error}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"binance_url_error:{exc.reason}") from exc

    def create_order(
        self,
        request: BinanceTestnetOrderRequest,
        *,
        dry_run: bool | None = None,
        test_order: bool = False,
    ) -> BinanceTestnetOrderResult:
        resolved_dry_run = env_bool("TESTNET_ORDER_LIFECYCLE_DRY_RUN", True) if dry_run is None else dry_run
        params = build_order_params(request)

        if resolved_dry_run:
            return BinanceTestnetOrderResult(
                action="CREATE",
                status="DRY_RUN",
                symbol=request.symbol,
                client_order_id=request.newClientOrderId,
                dry_run=True,
                request=params,
                response={
                    "message": "dry_run_create_order_skipped",
                    "test_order": test_order,
                },
            )

        if not test_order:
            assert_testnet_order_submission_allowed(self.config)
        else:
            readiness = evaluate_binance_testnet_readiness(self.config)
            if not readiness.ready:
                raise PermissionError(f"testnet_not_ready:{readiness.blockers}")

        path = "/fapi/v1/order/test" if test_order else "/fapi/v1/order"

        started = time.perf_counter()

        try:
            response = self._signed_request(
                method="POST",
                path=path,
                params=params,
            )
            latency_ms = (time.perf_counter() - started) * 1000

            return BinanceTestnetOrderResult(
                action="TEST" if test_order else "CREATE",
                status="SUBMITTED",
                symbol=request.symbol,
                order_id=response.get("orderId"),
                client_order_id=response.get("clientOrderId") or request.newClientOrderId,
                order_status=response.get("status"),
                dry_run=False,
                latency_ms=latency_ms,
                request=params,
                response=response,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000

            return BinanceTestnetOrderResult(
                action="TEST" if test_order else "CREATE",
                status="FAILED",
                symbol=request.symbol,
                client_order_id=request.newClientOrderId,
                dry_run=False,
                latency_ms=latency_ms,
                request=params,
                error=str(exc),
            )

    def query_order(
        self,
        *,
        symbol: str,
        order_id: int | str | None = None,
        client_order_id: str | None = None,
    ) -> BinanceTestnetOrderResult:
        params: dict[str, Any] = {
            "symbol": symbol,
            "orderId": order_id,
            "origClientOrderId": client_order_id,
            "recvWindow": env_int("TESTNET_ORDER_LIFECYCLE_RECV_WINDOW", 5000),
        }

        started = time.perf_counter()

        try:
            response = self._signed_request(
                method="GET",
                path="/fapi/v1/order",
                params=params,
            )
            latency_ms = (time.perf_counter() - started) * 1000

            return BinanceTestnetOrderResult(
                action="QUERY",
                status="QUERIED",
                symbol=symbol,
                order_id=response.get("orderId") or order_id,
                client_order_id=response.get("clientOrderId") or client_order_id,
                order_status=response.get("status"),
                dry_run=False,
                latency_ms=latency_ms,
                request={key: value for key, value in params.items() if value is not None},
                response=response,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000

            return BinanceTestnetOrderResult(
                action="QUERY",
                status="FAILED",
                symbol=symbol,
                order_id=order_id,
                client_order_id=client_order_id,
                dry_run=False,
                latency_ms=latency_ms,
                request={key: value for key, value in params.items() if value is not None},
                error=str(exc),
            )

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: int | str | None = None,
        client_order_id: str | None = None,
        dry_run: bool | None = None,
    ) -> BinanceTestnetOrderResult:
        resolved_dry_run = env_bool("TESTNET_ORDER_LIFECYCLE_DRY_RUN", True) if dry_run is None else dry_run

        params: dict[str, Any] = {
            "symbol": symbol,
            "orderId": order_id,
            "origClientOrderId": client_order_id,
            "recvWindow": env_int("TESTNET_ORDER_LIFECYCLE_RECV_WINDOW", 5000),
        }

        clean_params = {key: value for key, value in params.items() if value is not None}

        if resolved_dry_run:
            return BinanceTestnetOrderResult(
                action="CANCEL",
                status="DRY_RUN",
                symbol=symbol,
                order_id=order_id,
                client_order_id=client_order_id,
                dry_run=True,
                request=clean_params,
                response={"message": "dry_run_cancel_order_skipped"},
            )

        assert_testnet_order_submission_allowed(self.config)

        started = time.perf_counter()

        try:
            response = self._signed_request(
                method="DELETE",
                path="/fapi/v1/order",
                params=params,
            )
            latency_ms = (time.perf_counter() - started) * 1000

            return BinanceTestnetOrderResult(
                action="CANCEL",
                status="CANCELLED",
                symbol=symbol,
                order_id=response.get("orderId") or order_id,
                client_order_id=response.get("clientOrderId") or client_order_id,
                order_status=response.get("status"),
                dry_run=False,
                latency_ms=latency_ms,
                request=clean_params,
                response=response,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000

            return BinanceTestnetOrderResult(
                action="CANCEL",
                status="FAILED",
                symbol=symbol,
                order_id=order_id,
                client_order_id=client_order_id,
                dry_run=False,
                latency_ms=latency_ms,
                request=clean_params,
                error=str(exc),
            )


def export_order_lifecycle_result(
    result: BinanceTestnetOrderResult,
    *,
    output_dir: str | Path = "artifacts/testnet",
    name: str = "order_lifecycle_latest",
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path