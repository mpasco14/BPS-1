"""
Binance Futures candle series manager.

Responsabilidades:
- Manter buffers circulares de candles por timeframe.
- Foco atual: Binance Futures BTCUSDT.
- Suportar 5m, 15m, 1h e 1d.
- Garantir histórico mínimo para indicadores como EMA200.
- Evitar duplicidade de candles pelo open_time.
- Substituir candle ainda aberto quando chega atualização do mesmo open_time.
- Exportar série para pandas DataFrame.

Este módulo NÃO coleta dados da Binance.
Este módulo NÃO executa ordens.
Este módulo apenas organiza candles já normalizados.
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "1d"}


class Candle(BaseModel):
    """
    Candle OHLCV validado para strategy.

    Os campos seguem o padrão produzido por:
    - connectors/binance_ws.py
    - data/normalizer.py
    """

    model_config = ConfigDict(extra="allow")

    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str

    open_time: str | int
    close_time: str | int | None = None

    open: float
    high: float
    low: float
    close: float
    volume: float

    quote_volume: float | None = None
    trades_count: int | None = None
    taker_buy_base_volume: float | None = None
    taker_buy_quote_volume: float | None = None

    is_closed: bool = True

    funding_rate: float | None = None
    open_interest: float | None = None
    mark_price: float | None = None
    index_price: float | None = None

    received_at: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("symbol não pode ser vazio")

        return value

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        value = value.strip()

        aliases = {
            "5M": "5m",
            "5m": "5m",
            "15M": "15m",
            "15m": "15m",
            "1H": "1h",
            "1h": "1h",
            "1D": "1d",
            "1d": "1d",
        }

        normalized = aliases.get(value)

        if normalized not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"timeframe inválido: {value}")

        return normalized

    @field_validator("open", "high", "low", "close")
    @classmethod
    def price_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("preço precisa ser maior que zero")

        return float(value)

    @field_validator("volume")
    @classmethod
    def volume_must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("volume não pode ser negativo")

        return float(value)


def parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []

    return [item.strip() for item in value.split(",") if item.strip()]


def candle_sort_key(candle: Candle) -> str | int:
    return candle.open_time


@dataclass
class CandleBufferStats:
    timeframe: str
    size: int
    max_size: int
    ready_for_ema200: bool
    latest_open_time: str | int | None
    latest_close: float | None


class CandleSeriesStore:
    """
    Gerenciador de buffers circulares por timeframe.
    """

    def __init__(
        self,
        *,
        timeframes: list[str] | None = None,
        max_candles: int | None = None,
        min_candles_for_ema200: int | None = None,
    ) -> None:
        configured_timeframes = timeframes or parse_csv_env(
            os.getenv("STRATEGY_TIMEFRAMES", "5m,15m,1h,1d")
        )

        self.timeframes = [self._normalize_timeframe(tf) for tf in configured_timeframes]

        invalid = set(self.timeframes) - SUPPORTED_TIMEFRAMES

        if invalid:
            raise ValueError(f"timeframes não suportados: {sorted(invalid)}")

        self.max_candles = int(
            max_candles
            or os.getenv("STRATEGY_CANDLE_BUFFER_SIZE", "500")
        )

        self.min_candles_for_ema200 = int(
            min_candles_for_ema200
            or os.getenv("STRATEGY_MIN_CANDLES_FOR_EMA200", "200")
        )

        self._buffers: dict[str, deque[Candle]] = {
            timeframe: deque(maxlen=self.max_candles)
            for timeframe in self.timeframes
        }

    @staticmethod
    def _normalize_timeframe(timeframe: str) -> str:
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

        if normalized is None:
            raise ValueError(f"timeframe inválido: {timeframe}")

        return normalized

    def add_candle(self, timeframe: str, candle: Candle | dict[str, Any]) -> Candle:
        """
        Adiciona candle ao buffer.

        Se já existir candle com o mesmo open_time, substitui.
        Isso é importante para Binance Futures porque candles ainda abertos
        podem receber atualizações parciais.
        """
        tf = self._normalize_timeframe(timeframe)

        if tf not in self._buffers:
            self._buffers[tf] = deque(maxlen=self.max_candles)

        parsed = candle if isinstance(candle, Candle) else Candle.model_validate(candle)

        if parsed.timeframe != tf:
            parsed = parsed.model_copy(update={"timeframe": tf})

        buffer = self._buffers[tf]

        updated = False
        updated_items: list[Candle] = []

        for existing in buffer:
            if existing.open_time == parsed.open_time:
                updated_items.append(parsed)
                updated = True
            else:
                updated_items.append(existing)

        if not updated:
            updated_items.append(parsed)

        updated_items.sort(key=candle_sort_key)

        buffer.clear()
        buffer.extend(updated_items[-self.max_candles :])

        return parsed

    def get_candles(self, timeframe: str, n: int | None = None) -> list[Candle]:
        tf = self._normalize_timeframe(timeframe)
        candles = list(self._buffers.get(tf, []))

        candles.sort(key=candle_sort_key)

        if n is None:
            return candles

        return candles[-n:]

    def get_latest(self, timeframe: str) -> Candle | None:
        candles = self.get_candles(timeframe, n=1)

        if not candles:
            return None

        return candles[0]

    def is_ready(self, timeframe: str, min_candles: int | None = None) -> bool:
        required = min_candles or self.min_candles_for_ema200

        return len(self.get_candles(timeframe)) >= required

    def to_dataframe(self, timeframe: str, n: int | None = None) -> pd.DataFrame:
        candles = self.get_candles(timeframe, n=n)

        records = [candle.model_dump(mode="json") for candle in candles]

        if not records:
            return pd.DataFrame(
                columns=[
                    "venue",
                    "symbol",
                    "timeframe",
                    "open_time",
                    "close_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "quote_volume",
                    "trades_count",
                    "funding_rate",
                    "open_interest",
                    "mark_price",
                    "index_price",
                    "is_closed",
                ]
            )

        df = pd.DataFrame(records)

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
            "funding_rate",
            "open_interest",
            "mark_price",
            "index_price",
        ]

        for column in numeric_columns:
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")

        if "trades_count" in df.columns:
            df["trades_count"] = pd.to_numeric(df["trades_count"], errors="coerce")

        return df

    def stats(self, timeframe: str) -> CandleBufferStats:
        tf = self._normalize_timeframe(timeframe)
        candles = self.get_candles(tf)
        latest = candles[-1] if candles else None

        return CandleBufferStats(
            timeframe=tf,
            size=len(candles),
            max_size=self.max_candles,
            ready_for_ema200=self.is_ready(tf),
            latest_open_time=latest.open_time if latest else None,
            latest_close=latest.close if latest else None,
        )

    def all_stats(self) -> list[CandleBufferStats]:
        return [self.stats(timeframe) for timeframe in self.timeframes]


def build_candle_from_normalized_event(event: dict[str, Any]) -> Candle:
    """
    Converte saída de data/normalizer.py em Candle.
    """
    return Candle(
        venue="binance_futures",
        symbol=event.get("symbol", "BTCUSDT"),
        timeframe=event["timeframe"],
        open_time=event["open_time"],
        close_time=event.get("close_time"),
        open=event["open"],
        high=event["high"],
        low=event["low"],
        close=event["close"],
        volume=event["volume"],
        quote_volume=event.get("quote_volume"),
        trades_count=event.get("trades_count"),
        taker_buy_base_volume=event.get("taker_buy_base_volume"),
        taker_buy_quote_volume=event.get("taker_buy_quote_volume"),
        is_closed=event.get("is_closed", True),
        funding_rate=event.get("funding_rate"),
        open_interest=event.get("open_interest"),
        mark_price=event.get("mark_price"),
        index_price=event.get("index_price"),
        received_at=event.get("received_at"),
        raw=event.get("raw") or event,
    )