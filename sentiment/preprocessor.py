from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from sentiment.sentiment_schema import CleanSentimentItem, RawSentimentItem


load_dotenv()


BTC_TERMS = {
    "btc",
    "btcusdt",
    "bitcoin",
    "$btc",
    "#bitcoin",
    "#btc",
    "satoshi",
    "binance futures",
}

BULLISH_EMOJIS = {
    "🚀": " bullish_rocket ",
    "🌕": " bullish_moon ",
    "💎": " bullish_hodl ",
    "📈": " bullish_chart_up ",
}

BEARISH_EMOJIS = {
    "📉": " bearish_chart_down ",
    "🩸": " bearish_blood ",
    "💀": " bearish_risk ",
    "😱": " bearish_fear ",
}


class PreprocessConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    target_asset: str = "BTCUSDT"
    min_relevance_score: float = 0.50
    max_text_length: int = 5000
    keep_languages: list[str] = Field(default_factory=lambda: ["en", "pt", "unknown"])


class PreprocessResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_preprocessor"

    total_items: int
    clean_items_count: int
    duplicates_count: int
    irrelevant_count: int
    language_filtered_count: int

    items: list[dict[str, Any]] = Field(default_factory=list)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_preprocess_config() -> PreprocessConfig:
    return PreprocessConfig(
        target_asset=os.getenv("SENTIMENT_TARGET_ASSET", "BTCUSDT"),
        min_relevance_score=env_float("SENTIMENT_MIN_RELEVANCE_SCORE", 0.50),
        max_text_length=env_int("SENTIMENT_MAX_TEXT_LENGTH", 5000),
    )


def normalize_text(text: str) -> str:
    normalized = text or ""

    for emoji, replacement in BULLISH_EMOJIS.items():
        normalized = normalized.replace(emoji, replacement)

    for emoji, replacement in BEARISH_EMOJIS.items():
        normalized = normalized.replace(emoji, replacement)

    normalized = normalized.lower()
    normalized = re.sub(r"https?://\S+", " ", normalized)
    normalized = re.sub(r"@\w+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def detect_language(text: str) -> str:
    clean = normalize_text(text)

    portuguese_markers = {" que ", " de ", " para ", " mercado ", " alta ", " queda ", " preço "}
    english_markers = {" the ", " and ", " market ", " price ", " pump ", " dump ", " bullish ", " bearish "}

    padded = f" {clean} "

    pt_score = sum(1 for marker in portuguese_markers if marker in padded)
    en_score = sum(1 for marker in english_markers if marker in padded)

    if pt_score > en_score:
        return "pt"

    if en_score > pt_score:
        return "en"

    return "unknown"


def extract_symbols(text: str) -> list[str]:
    clean = normalize_text(text)
    symbols: set[str] = set()

    if any(term in clean for term in BTC_TERMS):
        symbols.add("BTCUSDT")

    cashtags = re.findall(r"\$[A-Z]{2,10}", text.upper())

    for cashtag in cashtags:
        if cashtag in {"$BTC", "$BTCUSDT"}:
            symbols.add("BTCUSDT")

    return sorted(symbols)


def relevance_score(text: str, target_asset: str = "BTCUSDT") -> float:
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "inflow",
        "outflow",
        "market sentiment",
        "buy pressure",
        "sell pressure",
        "pump",
        "dump",
        "bullish",
        "bearish",
        "moon",
        "panic",
        "fear",
        "greed",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
        "rompimento",
        "pânico",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    target_terms = {
        target_asset.lower(),
        target_asset.replace("USDT", "").lower(),
        f"${target_asset.replace('USDT', '').lower()}",
    }

    for term in target_terms:
        if term and term in clean:
            score += 0.20

    return min(1.0, score)
    clean = normalize_text(text)
    score = 0.0

    for term in BTC_TERMS:
        if term in clean:
            score += 0.25

    market_terms = {
        "price",
        "funding",
        "liquidation",
        "long",
        "short",
        "support",
        "resistance",
        "breakout",
        "volatility",
        "fomc",
        "cpi",
        "fed",
        "etf",
        "preço",
        "alta",
        "queda",
        "liquidação",
        "suporte",
        "resistência",
    }

    for term in market_terms:
        if term in clean:
            score += 0.08

    if target_asset.lower() in clean:
        score += 0.35

    return min(1.0, score)


def clean_raw_item(
    item: RawSentimentItem | dict[str, Any],
    *,
    config: PreprocessConfig | None = None,
    seen_hashes: set[str] | None = None,
) -> CleanSentimentItem:
    resolved_config = config or load_preprocess_config()
    raw = item if isinstance(item, RawSentimentItem) else RawSentimentItem.model_validate(item)

    truncated_text = raw.text[: resolved_config.max_text_length]
    clean_text = normalize_text(truncated_text)
    item_hash = text_hash(clean_text)
    language = raw.language or detect_language(clean_text)
    symbols = raw.symbols or extract_symbols(clean_text)
    relevance = relevance_score(clean_text, resolved_config.target_asset)

    if resolved_config.target_asset in symbols:
        relevance = min(1.0, relevance + 0.25)

    is_duplicate = item_hash in seen_hashes if seen_hashes is not None else False

    if seen_hashes is not None:
        seen_hashes.add(item_hash)

    return CleanSentimentItem(
        item_id=raw.item_id,
        source_type=raw.source_type,
        source_name=raw.source_name,
        original_text=raw.text,
        clean_text=clean_text,
        text_hash=item_hash,
        language=language,
        asset=raw.asset or resolved_config.target_asset,
        symbols=symbols,
        relevance_score=relevance,
        is_relevant=relevance >= resolved_config.min_relevance_score and resolved_config.target_asset in symbols,
        is_duplicate=is_duplicate,
        created_at=raw.created_at,
        collected_at=raw.collected_at,
        metadata=raw.metadata,
    )


def preprocess_sentiment_items(
    items: list[RawSentimentItem | dict[str, Any]],
    *,
    config: PreprocessConfig | None = None,
) -> PreprocessResult:
    resolved_config = config or load_preprocess_config()
    seen_hashes: set[str] = set()

    clean_items: list[CleanSentimentItem] = []
    duplicates_count = 0
    irrelevant_count = 0
    language_filtered_count = 0

    for item in items:
        clean_item = clean_raw_item(
            item,
            config=resolved_config,
            seen_hashes=seen_hashes,
        )

        if clean_item.is_duplicate:
            duplicates_count += 1
            continue

        if clean_item.language not in resolved_config.keep_languages:
            language_filtered_count += 1
            continue

        if not clean_item.is_relevant:
            irrelevant_count += 1
            continue

        clean_items.append(clean_item)

    return PreprocessResult(
        total_items=len(items),
        clean_items_count=len(clean_items),
        duplicates_count=duplicates_count,
        irrelevant_count=irrelevant_count,
        language_filtered_count=language_filtered_count,
        items=[item.model_dump(mode="json") for item in clean_items],
    )