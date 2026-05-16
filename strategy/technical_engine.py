"""
Binance Futures technical analysis engine.

Responsabilidades:
- Calcular indicadores técnicos por timeframe.
- Gerar sinais normalizados por indicador em [-1, +1].
- Gerar technical_score composto por timeframe.
- Usar pandas/numpy para evitar dependência obrigatória de TA-Lib.
- Ser testável, determinístico e independente de execução real.

Este módulo NÃO coleta dados.
Este módulo NÃO executa ordens.
Este módulo NÃO decide sozinho operar.
Ele apenas produz features técnicas para a strategy/risk engine.
"""

from __future__ import annotations

import math
import os
from typing import Any, Literal

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


Timeframe = Literal["5m", "15m", "1h", "1d"]

SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "1d"}


DEFAULT_SCORE_WEIGHTS: dict[str, dict[str, float]] = {
    "5m": {
        "ema_signal": 0.30,
        "vwap_signal": 0.25,
        "rsi_signal": 0.20,
        "volume_signal": 0.15,
        "macd_signal": 0.10,
    },
    "15m": {
        "ema_signal": 0.30,
        "rsi_signal": 0.20,
        "bb_signal": 0.20,
        "adx_signal": 0.20,
        "atr_signal": 0.10,
    },
    "1h": {
        "ema_signal": 0.30,
        "macd_signal": 0.20,
        "atr_signal": 0.15,
        "vwap_signal": 0.15,
        "funding_rate_signal": 0.20,
    },
    "1d": {
        "ema_signal": 0.35,
        "rsi_signal": 0.20,
        "realized_vol_signal": 0.20,
        "onchain_flow_signal": 0.25,
    },
}


class TechnicalSnapshot(BaseModel):
    """
    Snapshot técnico final para um timeframe.
    """

    model_config = ConfigDict(extra="allow")

    source: str = "technical_engine"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: Timeframe

    row_count: int
    latest_close: float
    latest_open_time: Any | None = None
    latest_close_time: Any | None = None

    indicators: dict[str, Any] = Field(default_factory=dict)
    signals: dict[str, float] = Field(default_factory=dict)

    technical_score: float
    is_ready: bool
    min_required_candles: int

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("symbol não pode ser vazio")

        return value

    @field_validator("technical_score")
    @classmethod
    def score_range(cls, value: float) -> float:
        if value < -1 or value > 1:
            raise ValueError("technical_score deve estar entre -1 e +1")

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


def clean_number(value: Any) -> float | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None

        return float(value)
    except (TypeError, ValueError):
        return None


def clean_indicator_dict(values: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}

    for key, value in values.items():
        if isinstance(value, (int, float, np.floating)):
            cleaned[key] = clean_number(value)
        else:
            cleaned[key] = value

    return cleaned


def prepare_ohlcv_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepara dataframe para cálculo técnico.

    Esperado:
    - open
    - high
    - low
    - close
    - volume

    Campos opcionais:
    - quote_volume
    - funding_rate
    - open_interest
    - mark_price
    - index_price
    """
    required_columns = {"open", "high", "low", "close", "volume"}
    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(f"DataFrame sem colunas obrigatórias: {sorted(missing)}")

    prepared = df.copy()

    if "open_time" in prepared.columns:
        prepared = prepared.sort_values("open_time")

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "funding_rate",
        "open_interest",
        "mark_price",
        "index_price",
        "onchain_flow_signal",
    ]

    for column in numeric_columns:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    prepared = prepared.dropna(subset=["open", "high", "low", "close", "volume"])

    if prepared.empty:
        raise ValueError("DataFrame sem candles válidos após limpeza")

    return prepared.reset_index(drop=True)


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))

    return result.fillna(50)


def macd(
    series: pd.Series,
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def true_range(df: pd.DataFrame) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = true_range(df)

    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    volume = df["volume"].replace(0, np.nan)

    cumulative_pv = (typical_price * volume).cumsum()
    cumulative_volume = volume.cumsum()

    return cumulative_pv / cumulative_volume


def bollinger_bands(
    series: pd.Series,
    *,
    period: int = 20,
    std_multiplier: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = series.rolling(window=period, min_periods=period).mean()
    std = series.rolling(window=period, min_periods=period).std()

    upper = middle + std_multiplier * std
    lower = middle - std_multiplier * std

    return upper, middle, lower


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )

    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    tr = true_range(df)
    atr_series = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_series
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_series

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)

    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def realized_volatility(close: pd.Series, window: int = 30) -> pd.Series:
    log_returns = np.log(close / close.shift())

    return log_returns.rolling(window=window, min_periods=window).std() * math.sqrt(365)


def volume_spike_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    baseline = volume.rolling(window=window, min_periods=window).mean()

    return volume / baseline.replace(0, np.nan)


def relation_signal(a: float | None, b: float | None, reference: float | None) -> float:
    """
    Sinal direcional baseado na relação entre dois valores.

    Exemplo:
    EMA rápida acima da EMA lenta → positivo.
    Close acima da VWAP → positivo.
    """
    if a is None or b is None or reference is None or reference <= 0:
        return 0.0

    pct_diff = (a - b) / reference

    return clamp(math.tanh(pct_diff * 25))


def rsi_signal(value: float | None) -> float:
    if value is None:
        return 0.0

    return clamp((value - 50.0) / 50.0)


def macd_signal(macd_hist: float | None, close: float | None) -> float:
    if macd_hist is None or close is None or close <= 0:
        return 0.0

    return clamp(math.tanh((macd_hist / close) * 100))


def atr_signal(value: float | None, close: float | None) -> float:
    """
    ATR é principalmente risco/volatilidade, não direção.

    Aqui tratamos ATR muito alto como penalidade leve.
    """
    if value is None or close is None or close <= 0:
        return 0.0

    atr_pct = value / close

    # Acima de ~2% de ATR vira penalidade relevante.
    return clamp(-atr_pct / 0.02)


def volume_signal(
    *,
    spike_ratio: float | None,
    open_price: float | None,
    close_price: float | None,
) -> float:
    if spike_ratio is None or open_price is None or close_price is None:
        return 0.0

    if spike_ratio <= 1.0:
        return 0.0

    direction = 1.0 if close_price >= open_price else -1.0
    strength = clamp((spike_ratio - 1.0) / 2.0, 0.0, 1.0)

    return direction * strength


def bollinger_signal(
    *,
    close: float | None,
    upper: float | None,
    middle: float | None,
    lower: float | None,
) -> float:
    if close is None or upper is None or middle is None or lower is None:
        return 0.0

    width = upper - lower

    if width <= 0:
        return 0.0

    if close <= lower:
        return 0.6

    if close >= upper:
        return -0.6

    return clamp(math.tanh((close - middle) / width * 2))


def adx_trend_signal(
    *,
    adx_value: float | None,
    ema_fast: float | None,
    ema_slow: float | None,
) -> float:
    if adx_value is None or ema_fast is None or ema_slow is None:
        return 0.0

    trend_direction = 1.0 if ema_fast >= ema_slow else -1.0
    trend_strength = clamp(adx_value / 50.0, 0.0, 1.0)

    return trend_direction * trend_strength


def funding_rate_signal(value: float | None) -> float:
    """
    Funding muito positivo pode indicar crowding long e risco contrarian.
    Funding negativo pode indicar crowding short e squeeze bullish.

    Regra inicial:
    +0.05% → sinal -1
    -0.05% → sinal +1
    """
    if value is None:
        return 0.0

    return clamp(-value / 0.0005)


def realized_vol_signal(value: float | None) -> float:
    """
    Volatilidade realizada não é direção, mas risco.

    Penaliza ambientes de volatilidade extrema.
    """
    if value is None:
        return 0.0

    return clamp(-value / 1.5)


def weighted_score(signals: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = sum(abs(weight) for weight in weights.values())

    if total_weight == 0:
        return 0.0

    raw_score = 0.0

    for signal_name, weight in weights.items():
        raw_score += signals.get(signal_name, 0.0) * weight

    return clamp(raw_score / total_weight)


def latest(series: pd.Series) -> float | None:
    if series.empty:
        return None

    return clean_number(series.iloc[-1])


def min_required_candles_for_timeframe(timeframe: str) -> int:
    if timeframe in {"1h", "1d"}:
        return 200

    if timeframe == "15m":
        return 50

    return 21


def calculate_technical_snapshot(
    *,
    timeframe: str,
    candles: pd.DataFrame,
    symbol: str = "BTCUSDT",
) -> TechnicalSnapshot:
    tf = normalize_timeframe(timeframe)
    df = prepare_ohlcv_dataframe(candles)

    row_count = len(df)
    latest_row = df.iloc[-1]
    close = clean_number(latest_row["close"])
    open_price = clean_number(latest_row["open"])

    if close is None:
        raise ValueError("Último candle sem close válido")

    indicators: dict[str, Any] = {}
    signals: dict[str, float] = {}

    if tf == "5m":
        ema_fast_period = int(os.getenv("TECH_5M_EMA_FAST", "9"))
        ema_slow_period = int(os.getenv("TECH_5M_EMA_SLOW", "21"))
        rsi_period = int(os.getenv("TECH_5M_RSI_PERIOD", "7"))
        atr_period = int(os.getenv("TECH_5M_ATR_PERIOD", "14"))
        volume_window = int(os.getenv("TECH_5M_VOLUME_SPIKE_WINDOW", "20"))

        ema_fast_series = ema(df["close"], ema_fast_period)
        ema_slow_series = ema(df["close"], ema_slow_period)
        rsi_series = rsi(df["close"], rsi_period)
        macd_line, macd_signal_line, macd_hist = macd(df["close"], fast=6, slow=13, signal=5)
        atr_series = atr(df, atr_period)
        vwap_series = vwap(df)
        volume_spike_series = volume_spike_ratio(df["volume"], volume_window)

        ema_fast = latest(ema_fast_series)
        ema_slow = latest(ema_slow_series)
        latest_vwap = latest(vwap_series)
        latest_rsi = latest(rsi_series)
        latest_macd_hist = latest(macd_hist)
        latest_atr = latest(atr_series)
        latest_volume_spike = latest(volume_spike_series)

        indicators.update(
            {
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "vwap": latest_vwap,
                "rsi": latest_rsi,
                "macd": latest(macd_line),
                "macd_signal": latest(macd_signal_line),
                "macd_hist": latest_macd_hist,
                "atr": latest_atr,
                "volume_spike_ratio": latest_volume_spike,
            }
        )

        signals.update(
            {
                "ema_signal": relation_signal(ema_fast, ema_slow, close),
                "vwap_signal": relation_signal(close, latest_vwap, close),
                "rsi_signal": rsi_signal(latest_rsi),
                "volume_signal": volume_signal(
                    spike_ratio=latest_volume_spike,
                    open_price=open_price,
                    close_price=close,
                ),
                "macd_signal": macd_signal(latest_macd_hist, close),
            }
        )

    elif tf == "15m":
        ema_fast_period = int(os.getenv("TECH_15M_EMA_FAST", "20"))
        ema_slow_period = int(os.getenv("TECH_15M_EMA_SLOW", "50"))
        rsi_period = int(os.getenv("TECH_15M_RSI_PERIOD", "14"))
        bb_period = int(os.getenv("TECH_15M_BB_PERIOD", "20"))
        adx_period = int(os.getenv("TECH_15M_ADX_PERIOD", "14"))

        ema_fast_series = ema(df["close"], ema_fast_period)
        ema_slow_series = ema(df["close"], ema_slow_period)
        rsi_series = rsi(df["close"], rsi_period)
        bb_upper, bb_middle, bb_lower = bollinger_bands(df["close"], period=bb_period)
        adx_series = adx(df, period=adx_period)
        atr_series = atr(df, period=14)

        ema_fast = latest(ema_fast_series)
        ema_slow = latest(ema_slow_series)
        latest_rsi = latest(rsi_series)
        latest_bb_upper = latest(bb_upper)
        latest_bb_middle = latest(bb_middle)
        latest_bb_lower = latest(bb_lower)
        latest_adx = latest(adx_series)
        latest_atr = latest(atr_series)

        indicators.update(
            {
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "rsi": latest_rsi,
                "bb_upper": latest_bb_upper,
                "bb_middle": latest_bb_middle,
                "bb_lower": latest_bb_lower,
                "adx": latest_adx,
                "atr": latest_atr,
            }
        )

        signals.update(
            {
                "ema_signal": relation_signal(ema_fast, ema_slow, close),
                "rsi_signal": rsi_signal(latest_rsi),
                "bb_signal": bollinger_signal(
                    close=close,
                    upper=latest_bb_upper,
                    middle=latest_bb_middle,
                    lower=latest_bb_lower,
                ),
                "adx_signal": adx_trend_signal(
                    adx_value=latest_adx,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                ),
                "atr_signal": atr_signal(latest_atr, close),
            }
        )

    elif tf == "1h":
        ema_fast_period = int(os.getenv("TECH_1H_EMA_FAST", "50"))
        ema_slow_period = int(os.getenv("TECH_1H_EMA_SLOW", "200"))
        atr_period = int(os.getenv("TECH_1H_ATR_PERIOD", "14"))
        macd_fast = int(os.getenv("TECH_1H_MACD_FAST", "12"))
        macd_slow = int(os.getenv("TECH_1H_MACD_SLOW", "26"))
        macd_signal_period = int(os.getenv("TECH_1H_MACD_SIGNAL", "9"))

        ema_fast_series = ema(df["close"], ema_fast_period)
        ema_slow_series = ema(df["close"], ema_slow_period)
        macd_line, macd_signal_line, macd_hist = macd(
            df["close"],
            fast=macd_fast,
            slow=macd_slow,
            signal=macd_signal_period,
        )
        atr_series = atr(df, atr_period)
        vwap_series = vwap(df)

        latest_funding_rate = clean_number(latest_row.get("funding_rate"))

        ema_fast = latest(ema_fast_series)
        ema_slow = latest(ema_slow_series)
        latest_macd_hist = latest(macd_hist)
        latest_atr = latest(atr_series)
        latest_vwap = latest(vwap_series)

        indicators.update(
            {
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "macd": latest(macd_line),
                "macd_signal": latest(macd_signal_line),
                "macd_hist": latest_macd_hist,
                "atr": latest_atr,
                "vwap": latest_vwap,
                "funding_rate": latest_funding_rate,
            }
        )

        signals.update(
            {
                "ema_signal": relation_signal(ema_fast, ema_slow, close),
                "macd_signal": macd_signal(latest_macd_hist, close),
                "atr_signal": atr_signal(latest_atr, close),
                "vwap_signal": relation_signal(close, latest_vwap, close),
                "funding_rate_signal": funding_rate_signal(latest_funding_rate),
            }
        )

    elif tf == "1d":
        ema_fast_period = int(os.getenv("TECH_1D_EMA_FAST", "50"))
        ema_slow_period = int(os.getenv("TECH_1D_EMA_SLOW", "200"))
        rsi_period = int(os.getenv("TECH_1D_RSI_PERIOD", "14"))
        realized_vol_window = int(os.getenv("TECH_1D_REALIZED_VOL_WINDOW", "30"))

        ema_fast_series = ema(df["close"], ema_fast_period)
        ema_slow_series = ema(df["close"], ema_slow_period)
        rsi_series = rsi(df["close"], rsi_period)
        realized_vol_series = realized_volatility(df["close"], window=realized_vol_window)

        ema_fast = latest(ema_fast_series)
        ema_slow = latest(ema_slow_series)
        latest_rsi = latest(rsi_series)
        latest_realized_vol = latest(realized_vol_series)

        onchain_flow = clean_number(latest_row.get("onchain_flow_signal")) or 0.0

        indicators.update(
            {
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "rsi": latest_rsi,
                "realized_vol": latest_realized_vol,
                "onchain_flow_signal": onchain_flow,
            }
        )

        signals.update(
            {
                "ema_signal": relation_signal(ema_fast, ema_slow, close),
                "rsi_signal": rsi_signal(latest_rsi),
                "realized_vol_signal": realized_vol_signal(latest_realized_vol),
                "onchain_flow_signal": clamp(onchain_flow),
            }
        )

    indicators = clean_indicator_dict(indicators)
    signals = {key: clamp(value) for key, value in signals.items()}

    score = weighted_score(
        signals=signals,
        weights=DEFAULT_SCORE_WEIGHTS[tf],
    )

    min_required = min_required_candles_for_timeframe(tf)

    latest_open_time = latest_row.get("open_time") if "open_time" in df.columns else None
    latest_close_time = latest_row.get("close_time") if "close_time" in df.columns else None

    return TechnicalSnapshot(
        symbol=symbol,
        timeframe=tf,
        row_count=row_count,
        latest_close=close,
        latest_open_time=latest_open_time,
        latest_close_time=latest_close_time,
        indicators=indicators,
        signals=signals,
        technical_score=score,
        is_ready=row_count >= min_required,
        min_required_candles=min_required,
    )


def calculate_many_timeframes(
    candles_by_timeframe: dict[str, pd.DataFrame],
    *,
    symbol: str = "BTCUSDT",
) -> dict[str, TechnicalSnapshot]:
    """
    Calcula snapshots para múltiplos timeframes.
    """
    snapshots: dict[str, TechnicalSnapshot] = {}

    for timeframe, candles in candles_by_timeframe.items():
        tf = normalize_timeframe(timeframe)
        snapshots[tf] = calculate_technical_snapshot(
            timeframe=tf,
            candles=candles,
            symbol=symbol,
        )

    return snapshots