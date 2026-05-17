"""
Binance Futures market selector.

Adaptação da ideia original de Polymarket:
- Não existem mercados com end_time para BTCUSDT perpetual.
- O equivalente operacional é selecionar símbolos ativos + timeframes permitidos.
- Regras de símbolo vêm de exchangeInfo.

Este módulo NÃO executa ordens.
"""

from __future__ import annotations

import os
import re
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "1d"}


class BinanceMarketCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    venue: str = "binance_futures"

    symbol: str
    base_asset: str
    quote_asset: str

    status: str
    contract_type: str | None = None

    timeframes: list[str] = Field(default_factory=list)

    filters: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


def normalize_timeframe(value: str) -> str:
    raw = value.strip()

    mapping = {
        "5M": "5m",
        "5m": "5m",
        "15M": "15m",
        "15m": "15m",
        "1H": "1h",
        "1h": "1h",
        "1D": "1d",
        "1d": "1d",
    }

    normalized = mapping.get(raw)

    if normalized not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"timeframe inválido: {value}")

    return normalized


def parse_configured_symbols() -> list[str]:
    raw = os.getenv("BINANCE_EXECUTION_SYMBOLS", "BTCUSDT")

    return [
        item.strip().upper()
        for item in raw.split(",")
        if item.strip()
    ]


def parse_configured_timeframes() -> list[str]:
    raw = os.getenv("BINANCE_EXECUTION_TIMEFRAMES", "5m,15m,1h,1d")

    return [
        normalize_timeframe(item)
        for item in raw.split(",")
        if item.strip()
    ]


def classify_timeframe_from_text(value: str) -> str | None:
    """
    Compatibilidade com o roadmap antigo:
    '5 minute' -> 5m
    'hourly'   -> 1h
    'daily'    -> 1d
    """
    text = value.lower()

    if re.search(r"\b5\s*(minute|min|m)\b", text):
        return "5m"

    if re.search(r"\b15\s*(minute|min|m)\b", text):
        return "15m"

    if "hourly" in text or re.search(r"\b1\s*(hour|h)\b", text):
        return "1h"

    if "daily" in text or re.search(r"\b1\s*(day|d)\b", text):
        return "1d"

    return None


def is_tradeable_symbol(symbol_info: dict[str, Any]) -> bool:
    if symbol_info.get("status") != "TRADING":
        return False

    contract_type = symbol_info.get("contractType")

    if contract_type and contract_type != "PERPETUAL":
        return False

    return True


def build_candidate(
    symbol_info: dict[str, Any],
    *,
    timeframes: list[str] | None = None,
) -> BinanceMarketCandidate:
    return BinanceMarketCandidate(
        symbol=str(symbol_info["symbol"]).upper(),
        base_asset=str(symbol_info.get("baseAsset", "")),
        quote_asset=str(symbol_info.get("quoteAsset", "")),
        status=str(symbol_info.get("status", "")),
        contract_type=symbol_info.get("contractType"),
        timeframes=timeframes or parse_configured_timeframes(),
        filters=list(symbol_info.get("filters") or []),
        raw=symbol_info,
    )


def select_markets_from_exchange_info(
    exchange_info: dict[str, Any],
    *,
    symbols: list[str] | None = None,
    quote_asset: str = "USDT",
    timeframes: list[str] | None = None,
) -> list[BinanceMarketCandidate]:
    wanted_symbols = set(symbols or parse_configured_symbols())
    selected_timeframes = timeframes or parse_configured_timeframes()

    candidates: list[BinanceMarketCandidate] = []

    for symbol_info in exchange_info.get("symbols", []):
        symbol = str(symbol_info.get("symbol", "")).upper()

        if wanted_symbols and symbol not in wanted_symbols:
            continue

        if str(symbol_info.get("quoteAsset", "")).upper() != quote_asset.upper():
            continue

        if not is_tradeable_symbol(symbol_info):
            continue

        candidates.append(
            build_candidate(
                symbol_info,
                timeframes=selected_timeframes,
            )
        )

    return candidates


def candidate_to_dict(candidate: BinanceMarketCandidate) -> dict[str, Any]:
    return candidate.model_dump(mode="json")