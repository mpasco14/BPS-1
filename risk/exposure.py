"""
Exposure tracking for Binance Futures.

Responsabilidades:
- Rastrear bankroll, daily PnL, posições abertas e exposição.
- Manter estado em memória ou Redis.
- Servir o risk_manager na aprovação de novos sinais.

Este módulo NÃO executa ordens.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


Direction = Literal["LONG", "SHORT"]


class ExposureSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_bankroll_usd: float
    daily_pnl_usd: float = 0.0

    open_positions: int = 0

    exposure_per_market: dict[str, float] = Field(default_factory=dict)
    exposure_by_timeframe: dict[str, float] = Field(default_factory=dict)

    btc_directional_exposure_usd: float = 0.0

    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def default_exposure_snapshot() -> ExposureSnapshot:
    return ExposureSnapshot(
        total_bankroll_usd=env_float("RISK_BANKROLL_USD", 2000.0),
        daily_pnl_usd=0.0,
        open_positions=0,
        exposure_per_market={},
        exposure_by_timeframe={},
        btc_directional_exposure_usd=0.0,
    )


def exposure_key() -> str:
    return os.getenv("EXPOSURE_REDIS_KEY", "btc_poly_bot:dev:risk:exposure")


def snapshot_to_json(snapshot: ExposureSnapshot) -> str:
    return json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)


def snapshot_from_json(payload: str) -> ExposureSnapshot:
    return ExposureSnapshot.model_validate(json.loads(payload))


class InMemoryExposureStore:
    def __init__(self, initial_snapshot: ExposureSnapshot | None = None) -> None:
        self.snapshot = initial_snapshot or default_exposure_snapshot()

    def load(self) -> ExposureSnapshot:
        return self.snapshot

    def save(self, snapshot: ExposureSnapshot) -> ExposureSnapshot:
        self.snapshot = snapshot
        return snapshot

    def reset(self) -> ExposureSnapshot:
        self.snapshot = default_exposure_snapshot()
        return self.snapshot


class RedisExposureStore:
    def __init__(
        self,
        *,
        redis_url: str | None = None,
        key: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.key = key or exposure_key()
        self.ttl_seconds = ttl_seconds or int(os.getenv("EXPOSURE_REDIS_TTL_SECONDS", "86400"))

        try:
            import redis  # type: ignore
        except ImportError as exc:
            raise RuntimeError("redis não está instalado. Use EXPOSURE_STORE_BACKEND=memory ou instale redis.") from exc

        self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)

    def load(self) -> ExposureSnapshot:
        payload = self.client.get(self.key)

        if not payload:
            snapshot = default_exposure_snapshot()
            self.save(snapshot)
            return snapshot

        return snapshot_from_json(payload)

    def save(self, snapshot: ExposureSnapshot) -> ExposureSnapshot:
        self.client.setex(self.key, self.ttl_seconds, snapshot_to_json(snapshot))
        return snapshot

    def reset(self) -> ExposureSnapshot:
        snapshot = default_exposure_snapshot()
        self.save(snapshot)
        return snapshot


def get_exposure_store():
    backend = os.getenv("EXPOSURE_STORE_BACKEND", "memory").strip().lower()

    if backend == "redis":
        return RedisExposureStore()

    return InMemoryExposureStore()


def signed_directional_exposure(
    *,
    direction: Direction,
    exposure_usd: float,
) -> float:
    if direction == "LONG":
        return abs(exposure_usd)

    return -abs(exposure_usd)


def apply_fill_to_exposure(
    snapshot: ExposureSnapshot,
    *,
    symbol: str,
    timeframe: str,
    direction: Direction,
    margin_usd: float,
) -> ExposureSnapshot:
    symbol = symbol.upper()
    timeframe = timeframe.lower()

    exposure_per_market = dict(snapshot.exposure_per_market)
    exposure_by_timeframe = dict(snapshot.exposure_by_timeframe)

    exposure_per_market[symbol] = exposure_per_market.get(symbol, 0.0) + margin_usd
    exposure_by_timeframe[timeframe] = exposure_by_timeframe.get(timeframe, 0.0) + margin_usd

    directional = snapshot.btc_directional_exposure_usd + signed_directional_exposure(
        direction=direction,
        exposure_usd=margin_usd,
    )

    return snapshot.model_copy(
        update={
            "open_positions": snapshot.open_positions + 1,
            "exposure_per_market": exposure_per_market,
            "exposure_by_timeframe": exposure_by_timeframe,
            "btc_directional_exposure_usd": directional,
            "updated_at": datetime.now(timezone.utc),
        }
    )


def apply_close_to_exposure(
    snapshot: ExposureSnapshot,
    *,
    symbol: str,
    timeframe: str,
    direction: Direction,
    margin_usd: float,
    realized_pnl_usd: float,
) -> ExposureSnapshot:
    symbol = symbol.upper()
    timeframe = timeframe.lower()

    exposure_per_market = dict(snapshot.exposure_per_market)
    exposure_by_timeframe = dict(snapshot.exposure_by_timeframe)

    exposure_per_market[symbol] = max(0.0, exposure_per_market.get(symbol, 0.0) - margin_usd)
    exposure_by_timeframe[timeframe] = max(0.0, exposure_by_timeframe.get(timeframe, 0.0) - margin_usd)

    directional = snapshot.btc_directional_exposure_usd - signed_directional_exposure(
        direction=direction,
        exposure_usd=margin_usd,
    )

    return snapshot.model_copy(
        update={
            "daily_pnl_usd": snapshot.daily_pnl_usd + realized_pnl_usd,
            "open_positions": max(0, snapshot.open_positions - 1),
            "exposure_per_market": exposure_per_market,
            "exposure_by_timeframe": exposure_by_timeframe,
            "btc_directional_exposure_usd": directional,
            "updated_at": datetime.now(timezone.utc),
        }
    )


def exposure_pct(snapshot: ExposureSnapshot, value_usd: float) -> float:
    if snapshot.total_bankroll_usd <= 0:
        return 0.0

    return value_usd / snapshot.total_bankroll_usd