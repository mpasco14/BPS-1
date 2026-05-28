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


BinanceErrorCategory = Literal[
    "NONE",
    "RATE_LIMIT",
    "TIMESTAMP",
    "AUTH",
    "SIGNATURE",
    "ORDER_REJECTED",
    "INSUFFICIENT_MARGIN",
    "SERVER",
    "NETWORK",
    "UNKNOWN",
]


class BinanceAPIErrorClassification(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_testnet_api_error_classifier"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    category: BinanceErrorCategory
    retryable: bool
    should_backoff: bool

    http_status: int | None = None
    error_code: int | None = None
    message: str = ""

    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def classify_binance_api_error(
    *,
    http_status: int | None = None,
    error_code: int | None = None,
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> BinanceAPIErrorClassification:
    category: BinanceErrorCategory = "NONE"
    retryable = False
    should_backoff = False
    recommendations: list[str] = []

    normalized_message = message.lower()

    if http_status in {418, 429} or error_code in {-1003}:
        category = "RATE_LIMIT"
        retryable = True
        should_backoff = True
        recommendations.append("Aplicar backoff, reduzir frequência e revisar limites de ordem/API.")

    elif error_code in {-1021} or "timestamp" in normalized_message:
        category = "TIMESTAMP"
        retryable = True
        should_backoff = False
        recommendations.append("Sincronizar relógio local e revisar recvWindow/timestamp.")

    elif error_code in {-1022} or "signature" in normalized_message:
        category = "SIGNATURE"
        retryable = False
        should_backoff = False
        recommendations.append("Revisar assinatura HMAC, query string e API secret.")

    elif error_code in {-2014, -2015} or "api-key" in normalized_message or "invalid api" in normalized_message:
        category = "AUTH"
        retryable = False
        should_backoff = False
        recommendations.append("Revisar API key/secret, permissões e ambiente testnet.")

    elif error_code in {-2019} or "margin" in normalized_message:
        category = "INSUFFICIENT_MARGIN"
        retryable = False
        should_backoff = False
        recommendations.append("Reduzir notional/leverage ou revisar saldo testnet.")

    elif error_code in {-2010, -2021, -2022}:
        category = "ORDER_REJECTED"
        retryable = False
        should_backoff = False
        recommendations.append("Revisar parâmetros da ordem e regras do símbolo.")

    elif http_status in {500, 502, 503, 504}:
        category = "SERVER"
        retryable = True
        should_backoff = True
        recommendations.append("Erro de servidor; retry com backoff e limite conservador.")

    elif http_status is None and message:
        category = "NETWORK"
        retryable = True
        should_backoff = True
        recommendations.append("Erro de rede/local; retry controlado e registrar incidente.")

    elif http_status and http_status >= 400:
        category = "UNKNOWN"
        retryable = False
        should_backoff = False
        recommendations.append("Erro não classificado; bloquear execução e revisar resposta.")

    return BinanceAPIErrorClassification(
        category=category,
        retryable=retryable,
        should_backoff=should_backoff,
        http_status=http_status,
        error_code=error_code,
        message=message,
        recommendations=sorted(set(recommendations)),
        metadata=metadata or {},
    )


def export_binance_api_error_classification(
    classification: BinanceAPIErrorClassification,
    *,
    output_dir: str | Path | None = None,
    name: str = "binance_api_error_classification",
) -> Path:
    path = Path(output_dir or os.getenv("BINANCE_TESTNET_API_ERROR_OUTPUT_DIR", "artifacts/binance_testnet_adapter"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(classification.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path