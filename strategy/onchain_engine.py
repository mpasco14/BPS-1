"""
Binance Futures on-chain strategy engine.

Responsabilidades:
- Converter eventos on-chain em sinais normalizados.
- Usar dados gratuitos atuais:
  - mempool_fees
  - mempool_stats
  - stablecoin_supply
  - block_tip_height
- Manter compatibilidade futura com métricas premium:
  - whale_inflow
  - whale_outflow
  - stablecoin_inflow
  - miner_outflow
  - exchange_inflow
  - exchange_outflow
- Gerar onchain_score por timeframe em [-1, +1].

Este módulo NÃO coleta dados externos.
Este módulo NÃO executa ordens.
Este módulo NÃO substitui o risk manager.
"""

from __future__ import annotations

import math
import os
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


Timeframe = Literal["5m", "15m", "1h", "1d"]

SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "1d"}


DEFAULT_TIMEFRAME_WEIGHTS = {
    "5m": 0.05,
    "15m": 0.10,
    "1h": 0.25,
    "1d": 0.40,
}


class OnchainEvent(BaseModel):
    """
    Evento on-chain normalizado para análise de strategy.
    """

    model_config = ConfigDict(extra="allow")

    source: str = "onchain"
    provider: str = "unknown"

    event_type: str
    asset: str = "BTC"
    category: str = "unknown"
    interval: str = "snapshot"

    timestamp: int | None = None
    collected_at: str | None = None

    value: Any = None
    score: float | None = None

    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("asset")
    @classmethod
    def normalize_asset(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("asset não pode ser vazio")

        return value

    @field_validator("event_type")
    @classmethod
    def normalize_event_type(cls, value: str) -> str:
        value = value.strip().lower()

        if not value:
            raise ValueError("event_type não pode ser vazio")

        return value


class OnchainSnapshot(BaseModel):
    """
    Resultado agregado da análise on-chain para um timeframe.
    """

    model_config = ConfigDict(extra="allow")

    source: str = "onchain_engine"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: Timeframe

    raw_onchain_score: float
    timeframe_weight: float
    onchain_score: float

    component_signals: dict[str, float] = Field(default_factory=dict)
    component_weights: dict[str, float] = Field(default_factory=dict)

    event_count: int
    is_ready: bool

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("symbol não pode ser vazio")

        return value

    @field_validator("raw_onchain_score", "onchain_score")
    @classmethod
    def score_range(cls, value: float) -> float:
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

    normalized = mapping.get(timeframe.strip())

    if normalized not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"timeframe não suportado: {timeframe}")

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


def env_float(name: str, default: float) -> float:
    value = safe_float(os.getenv(name))

    if value is None:
        return default

    return value


def get_timeframe_weight(timeframe: str) -> float:
    tf = normalize_timeframe(timeframe)

    env_names = {
        "5m": "ONCHAIN_WEIGHT_5M",
        "15m": "ONCHAIN_WEIGHT_15M",
        "1h": "ONCHAIN_WEIGHT_1H",
        "1d": "ONCHAIN_WEIGHT_1D",
    }

    return clamp(
        env_float(env_names[tf], DEFAULT_TIMEFRAME_WEIGHTS[tf]),
        lower=0.0,
        upper=1.0,
    )


def normalize_onchain_event(raw: dict[str, Any]) -> OnchainEvent:
    """
    Aceita eventos vindos de:
    - connectors/free_onchain.py
    - data/normalizer.py
    - eventos premium futuros

    Campos possíveis:
    - event_type
    - metric
    """
    event_type = raw.get("event_type") or raw.get("metric") or "unknown"

    return OnchainEvent(
        source=str(raw.get("source") or "onchain"),
        provider=str(raw.get("provider") or raw.get("source") or "unknown"),
        event_type=str(event_type),
        asset=str(raw.get("asset") or "BTC"),
        category=str(raw.get("category") or "unknown"),
        interval=str(raw.get("interval") or "snapshot"),
        timestamp=raw.get("timestamp"),
        collected_at=raw.get("collected_at"),
        value=raw.get("value"),
        score=safe_float(raw.get("score")),
        raw=raw,
    )


def extract_nested_score(value: Any, *keys: str) -> float | None:
    """
    Tenta extrair score/valor numérico de dicts aninhados.
    """
    if not isinstance(value, dict):
        return safe_float(value)

    for key in keys:
        if key in value:
            found = safe_float(value.get(key))

            if found is not None:
                return found

    return None


def score_from_event(event: OnchainEvent) -> float:
    """
    Converte um evento on-chain em sinal direcional [-1, +1].

    Regra geral:
    - score do conector costuma representar intensidade, não direção.
    - aqui damos direção conforme o tipo do evento.
    """
    event_type = event.event_type.lower()
    raw_score = event.score

    if raw_score is None:
        raw_score = extract_nested_score(
            event.value,
            "score",
            "supply_change_pct",
            "change_pct",
            "netflow_score",
        )

    intensity = clamp(raw_score or 0.0, lower=0.0, upper=1.0)

    # Dados gratuitos atuais.
    if event_type in {"mempool_fees", "fee_pressure", "network_fee_pressure"}:
        # Fee alta = leve bearish/risk-off.
        return clamp(-intensity)

    if event_type in {"mempool_stats", "mempool_congestion", "network_congestion"}:
        # Congestionamento alto = leve bearish/risk-off.
        return clamp(-intensity)

    if event_type in {"stablecoin_supply", "stablecoin_liquidity"}:
        # Liquidez de stablecoins alta = leve bullish.
        # Como supply absoluto não é direção perfeita, reduzimos a força.
        return clamp(intensity * 0.50)

    if event_type in {"block_tip_height", "block_height"}:
        return 0.0

    # Métricas premium/futuras.
    if event_type in {"whale_inflow", "exchange_whale_inflow"}:
        return clamp(-intensity)

    if event_type in {"whale_outflow", "exchange_whale_outflow"}:
        return clamp(intensity)

    if event_type in {"stablecoin_inflow", "stablecoin_exchange_inflow"}:
        return clamp(intensity)

    if event_type in {"stablecoin_outflow", "stablecoin_exchange_outflow"}:
        return clamp(-intensity)

    if event_type in {"miner_outflow", "miner_selling", "miner_net_outflow"}:
        return clamp(-intensity)

    if event_type in {"miner_inflow", "miner_accumulation"}:
        return clamp(intensity)

    if event_type in {"exchange_inflow", "exchange_net_inflow"}:
        return clamp(-intensity)

    if event_type in {"exchange_outflow", "exchange_net_outflow"}:
        return clamp(intensity)

    if event_type in {"exchange_netflow"}:
        value = extract_nested_score(event.value, "netflow", "value")

        if value is None:
            return 0.0

        # Netflow positivo para exchanges tende a ser bearish.
        return clamp(math.tanh(-value))

    return 0.0


def weight_for_event_type(event_type: str) -> float:
    event_type = event_type.lower()

    if event_type in {"mempool_fees", "fee_pressure", "network_fee_pressure"}:
        return env_float("ONCHAIN_MEMPOOL_FEES_WEIGHT", 0.35)

    if event_type in {"mempool_stats", "mempool_congestion", "network_congestion"}:
        return env_float("ONCHAIN_MEMPOOL_STATS_WEIGHT", 0.25)

    if event_type in {"stablecoin_supply", "stablecoin_liquidity"}:
        return env_float("ONCHAIN_STABLECOIN_SUPPLY_WEIGHT", 0.40)

    if event_type in {"whale_inflow", "exchange_whale_inflow"}:
        return env_float("ONCHAIN_WHALE_INFLOW_WEIGHT", 0.35)

    if event_type in {"whale_outflow", "exchange_whale_outflow"}:
        return env_float("ONCHAIN_WHALE_OUTFLOW_WEIGHT", 0.35)

    if event_type in {"stablecoin_inflow", "stablecoin_exchange_inflow"}:
        return env_float("ONCHAIN_STABLECOIN_INFLOW_WEIGHT", 0.30)

    if event_type in {"miner_outflow", "miner_selling", "miner_net_outflow"}:
        return env_float("ONCHAIN_MINER_OUTFLOW_WEIGHT", 0.25)

    if event_type in {"exchange_inflow", "exchange_net_inflow"}:
        return env_float("ONCHAIN_EXCHANGE_INFLOW_WEIGHT", 0.30)

    if event_type in {"exchange_outflow", "exchange_net_outflow"}:
        return env_float("ONCHAIN_EXCHANGE_OUTFLOW_WEIGHT", 0.30)

    return 0.0


def aggregate_onchain_events(events: list[OnchainEvent]) -> tuple[float, dict[str, float], dict[str, float]]:
    """
    Agrega eventos em raw_onchain_score [-1, +1].
    """
    weighted_sum = 0.0
    total_weight = 0.0

    component_signals: dict[str, float] = {}
    component_weights: dict[str, float] = {}

    for event in events:
        signal = score_from_event(event)
        weight = weight_for_event_type(event.event_type)

        component_signals[event.event_type] = signal
        component_weights[event.event_type] = weight

        if weight <= 0:
            continue

        weighted_sum += signal * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.0, component_signals, component_weights

    return clamp(weighted_sum / total_weight), component_signals, component_weights


def calculate_onchain_snapshot(
    *,
    timeframe: str,
    events: list[dict[str, Any]] | list[OnchainEvent],
    symbol: str = "BTCUSDT",
) -> OnchainSnapshot:
    tf = normalize_timeframe(timeframe)

    normalized_events = [
        event if isinstance(event, OnchainEvent) else normalize_onchain_event(event)
        for event in events
    ]

    raw_score, component_signals, component_weights = aggregate_onchain_events(normalized_events)
    timeframe_weight = get_timeframe_weight(tf)

    final_score = clamp(raw_score * timeframe_weight)

    return OnchainSnapshot(
        symbol=symbol,
        timeframe=tf,
        raw_onchain_score=raw_score,
        timeframe_weight=timeframe_weight,
        onchain_score=final_score,
        component_signals=component_signals,
        component_weights=component_weights,
        event_count=len(normalized_events),
        is_ready=len(normalized_events) > 0,
    )


def calculate_many_timeframes(
    events: list[dict[str, Any]] | list[OnchainEvent],
    *,
    symbol: str = "BTCUSDT",
    timeframes: list[str] | None = None,
) -> dict[str, OnchainSnapshot]:
    selected_timeframes = timeframes or ["5m", "15m", "1h", "1d"]

    snapshots: dict[str, OnchainSnapshot] = {}

    for timeframe in selected_timeframes:
        tf = normalize_timeframe(timeframe)
        snapshots[tf] = calculate_onchain_snapshot(
            timeframe=tf,
            events=events,
            symbol=symbol,
        )

    return snapshots


def snapshot_to_dict(snapshot: OnchainSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(mode="json")