"""
Binance Futures signal engine.

Responsabilidades:
- Converter feature snapshots em sinais LONG / SHORT / HOLD.
- Aplicar thresholds por timeframe.
- Bloquear sinais com book ruim, spread alto, liquidez baixa ou dados vencidos.
- Gerar saída auditável para risk_manager e paper_executor.

Este módulo NÃO executa ordens.
Este módulo NÃO calcula tamanho de posição.
Este módulo NÃO substitui risk_manager.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


Direction = Literal["LONG", "SHORT", "HOLD"]
SignalDecision = Literal["ENTER", "NO_TRADE", "BLOCKED"]
Timeframe = Literal["5m", "15m", "1h", "1d"]


SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "1d"}


class FeatureInput(BaseModel):
    """
    Entrada normalizada para o signal engine.

    Aceita snapshots vindos de:
    - data/feature_store.py
    - dicts vindos de eventos Kafka/Redis
    """

    model_config = ConfigDict(extra="allow")

    timestamp: Any | None = None

    venue: str = "binance_futures"
    instrument_id: str = "BTCUSDT"
    symbol: str = "BTCUSDT"
    timeframe: Timeframe

    tech_score: float
    onchain_score: float = 0.0
    sentiment_score: float = 0.0
    microstructure_score: float = 0.0
    combined_score: float

    binance_spread_pct: float | None = None
    binance_liquidity_usd: float | None = None

    funding_rate: float | None = None
    open_interest: float | None = None
    mark_price: float | None = None
    index_price: float | None = None

    btc_features: dict[str, Any] = Field(default_factory=dict)
    raw_components: dict[str, Any] = Field(default_factory=dict)

    @field_validator("venue")
    @classmethod
    def normalize_venue(cls, value: str) -> str:
        value = value.strip().lower()

        if not value:
            raise ValueError("venue não pode ser vazio")

        return value

    @field_validator("instrument_id", "symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("symbol não pode ser vazio")

        return value

    @field_validator("timeframe", mode="before")
    @classmethod
    def normalize_timeframe_field(cls, value: str) -> str:
        return normalize_timeframe(value)

    @field_validator(
        "tech_score",
        "onchain_score",
        "sentiment_score",
        "microstructure_score",
        "combined_score",
    )
    @classmethod
    def validate_score(cls, value: float) -> float:
        if value < -1 or value > 1:
            raise ValueError("score deve estar entre -1 e +1")

        return float(value)


class TradingSignal(BaseModel):
    """
    Saída auditável do signal engine.
    """

    model_config = ConfigDict(extra="allow")

    source: str = "signal_engine"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    instrument_id: str = "BTCUSDT"
    timeframe: Timeframe

    direction: Direction
    decision: SignalDecision

    confidence: float
    threshold: float

    combined_score: float
    tech_score: float
    microstructure_score: float
    onchain_score: float
    sentiment_score: float

    blockers: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    feature_timestamp: datetime | None = None

    raw_features: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("confidence deve estar entre 0 e 1")

        return float(value)

    @field_validator("combined_score", "tech_score", "microstructure_score", "onchain_score", "sentiment_score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if value < -1 or value > 1:
            raise ValueError("score deve estar entre -1 e +1")

        return float(value)


def normalize_timeframe(timeframe: str) -> Timeframe:
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

    normalized = mapping.get(str(timeframe).strip())

    if normalized not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"timeframe inválido: {timeframe}")

    return normalized  # type: ignore[return-value]


def clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    value = safe_float(os.getenv(name))

    if value is None:
        return default

    return value


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return None

        if stripped.isdigit():
            return parse_timestamp(int(stripped))

        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    numeric = safe_float(value)

    if numeric is None:
        return None

    numeric_int = int(numeric)

    if numeric_int >= 1_000_000_000_000:
        numeric_int = numeric_int // 1000

    return datetime.fromtimestamp(numeric_int, tz=timezone.utc)


def current_utc() -> datetime:
    return datetime.now(timezone.utc)


def seconds_since(timestamp: datetime | None, *, now: datetime | None = None) -> float | None:
    if timestamp is None:
        return None

    reference = now or current_utc()

    return max(0.0, (reference - timestamp).total_seconds())


def get_threshold_for_timeframe(timeframe: str) -> float:
    tf = normalize_timeframe(timeframe)

    env_names = {
        "5m": "MIN_COMBINED_SCORE_5M",
        "15m": "MIN_COMBINED_SCORE_15M",
        "1h": "MIN_COMBINED_SCORE_1H",
        "1d": "MIN_COMBINED_SCORE_1D",
    }

    defaults = {
        "5m": 0.35,
        "15m": 0.30,
        "1h": 0.25,
        "1d": 0.20,
    }

    return env_float(env_names[tf], defaults[tf])


def get_allowed_directions() -> str:
    value = os.getenv("SIGNAL_ALLOWED_DIRECTIONS", "both").strip().lower()

    if value not in {"both", "long_only", "short_only"}:
        return "both"

    return value


def infer_direction(
    *,
    combined_score: float,
    threshold: float,
    allowed_directions: str | None = None,
) -> Direction:
    allowed = allowed_directions or get_allowed_directions()

    if combined_score >= threshold and allowed in {"both", "long_only"}:
        return "LONG"

    if combined_score <= -threshold and allowed in {"both", "short_only"}:
        return "SHORT"

    return "HOLD"


def calculate_confidence(
    *,
    combined_score: float,
    threshold: float,
) -> float:
    if threshold <= 0:
        return min(abs(combined_score), 1.0)

    # threshold = início do sinal. Score 1.0 = confiança 1.0.
    if abs(combined_score) < threshold:
        return 0.0

    confidence = (abs(combined_score) - threshold) / max(1.0 - threshold, 1e-9)

    return min(1.0, max(0.0, confidence))


def extract_orderbook_analysis(features: FeatureInput) -> dict[str, Any]:
    """
    Tenta encontrar dados de orderbook nos formatos usados no projeto.
    """
    btc_features = features.btc_features or {}
    raw_components = features.raw_components or {}

    orderbook = btc_features.get("orderbook")

    if isinstance(orderbook, dict):
        return orderbook

    raw_orderbook = raw_components.get("orderbook")

    if isinstance(raw_orderbook, dict):
        analysis = raw_orderbook.get("analysis")

        if isinstance(analysis, dict):
            return analysis

        return raw_orderbook

    return {}


def is_orderbook_tradeable(features: FeatureInput) -> bool | None:
    analysis = extract_orderbook_analysis(features)

    value = analysis.get("is_tradeable")

    if value is None:
        return None

    return bool(value)


def get_orderbook_blockers(features: FeatureInput) -> list[str]:
    analysis = extract_orderbook_analysis(features)

    blockers = analysis.get("blockers")

    if isinstance(blockers, list):
        return [str(item) for item in blockers]

    return []


def validate_market_quality(features: FeatureInput) -> list[str]:
    blockers: list[str] = []

    require_tradeable_book = parse_bool(
        os.getenv("SIGNAL_REQUIRE_TRADEABLE_BOOK"),
        default=True,
    )

    if require_tradeable_book:
        tradeable = is_orderbook_tradeable(features)

        if tradeable is False:
            blockers.append("orderbook_not_tradeable")

        for blocker in get_orderbook_blockers(features):
            blockers.append(f"orderbook_{blocker}")

    max_spread = env_float("SIGNAL_MAX_SPREAD_PCT", env_float("MAX_SPREAD_PCT", 0.002))
    min_liquidity = env_float("SIGNAL_MIN_LIQUIDITY_USD", env_float("MIN_LIQUIDITY_USD", 50000))

    if features.binance_spread_pct is not None and features.binance_spread_pct > max_spread:
        blockers.append("spread_too_wide")

    if features.binance_liquidity_usd is not None and features.binance_liquidity_usd < min_liquidity:
        blockers.append("insufficient_liquidity")

    return blockers


def validate_staleness(features: FeatureInput, *, now: datetime | None = None) -> list[str]:
    blockers: list[str] = []

    timestamp = parse_timestamp(features.timestamp)

    max_feature_age = env_float("SIGNAL_MAX_FEATURE_STALENESS_SECONDS", 300)

    age = seconds_since(timestamp, now=now)

    if age is None:
        blockers.append("missing_feature_timestamp")
    elif age > max_feature_age:
        blockers.append("feature_snapshot_stale")

    return blockers


def validate_microstructure_alignment(
    *,
    direction: Direction,
    microstructure_score: float,
) -> list[str]:
    blockers: list[str] = []

    if direction == "HOLD":
        return blockers

    required = parse_bool(
        os.getenv("SIGNAL_REQUIRE_MICROSTRUCTURE_ALIGNMENT"),
        default=True,
    )

    if not required:
        return blockers

    threshold = env_float("SIGNAL_MICROSTRUCTURE_CONTRADICTION_THRESHOLD", 0.25)

    if direction == "LONG" and microstructure_score <= -threshold:
        blockers.append("microstructure_contradicts_long")

    if direction == "SHORT" and microstructure_score >= threshold:
        blockers.append("microstructure_contradicts_short")

    return blockers


def build_reasons(features: FeatureInput, direction: Direction, threshold: float) -> list[str]:
    reasons: list[str] = []

    if direction == "LONG":
        reasons.append(f"combined_score_above_threshold:{features.combined_score:.6f}>={threshold:.6f}")

    elif direction == "SHORT":
        reasons.append(f"combined_score_below_negative_threshold:{features.combined_score:.6f}<=-{threshold:.6f}")

    else:
        reasons.append(f"combined_score_inside_hold_zone:{features.combined_score:.6f}")

    if features.tech_score != 0:
        reasons.append(f"technical_score:{features.tech_score:.6f}")

    if features.microstructure_score != 0:
        reasons.append(f"microstructure_score:{features.microstructure_score:.6f}")

    if features.onchain_score != 0:
        reasons.append(f"onchain_score:{features.onchain_score:.6f}")

    if features.sentiment_score != 0:
        reasons.append(f"sentiment_score:{features.sentiment_score:.6f}")

    return reasons


def generate_signal(
    feature_snapshot: FeatureInput | dict[str, Any],
    *,
    now: datetime | None = None,
) -> TradingSignal:
    features = (
        feature_snapshot
        if isinstance(feature_snapshot, FeatureInput)
        else FeatureInput.model_validate(feature_snapshot)
    )

    threshold = get_threshold_for_timeframe(features.timeframe)
    direction = infer_direction(
        combined_score=features.combined_score,
        threshold=threshold,
    )

    confidence = calculate_confidence(
        combined_score=features.combined_score,
        threshold=threshold,
    )

    blockers: list[str] = []

    blockers.extend(validate_staleness(features, now=now))
    blockers.extend(validate_market_quality(features))
    blockers.extend(
        validate_microstructure_alignment(
            direction=direction,
            microstructure_score=features.microstructure_score,
        )
    )

    min_confidence = env_float("MIN_CONFIDENCE", 0.65)

    if direction != "HOLD" and confidence < min_confidence:
        blockers.append("confidence_below_minimum")

    reasons = build_reasons(features, direction, threshold)

    if blockers:
        decision: SignalDecision = "BLOCKED"
    elif direction == "HOLD":
        decision = "NO_TRADE"
    else:
        decision = "ENTER"

    feature_timestamp = parse_timestamp(features.timestamp)

    return TradingSignal(
        venue=features.venue,
        symbol=features.symbol,
        instrument_id=features.instrument_id,
        timeframe=features.timeframe,
        direction=direction,
        decision=decision,
        confidence=confidence,
        threshold=threshold,
        combined_score=features.combined_score,
        tech_score=features.tech_score,
        microstructure_score=features.microstructure_score,
        onchain_score=features.onchain_score,
        sentiment_score=features.sentiment_score,
        blockers=blockers,
        reasons=reasons,
        feature_timestamp=feature_timestamp,
        raw_features=features.model_dump(mode="json"),
    )


def signal_to_dict(signal: TradingSignal) -> dict[str, Any]:
    return signal.model_dump(mode="json")


def should_forward_to_risk_manager(signal: TradingSignal) -> bool:
    return signal.decision == "ENTER" and signal.direction in {"LONG", "SHORT"}