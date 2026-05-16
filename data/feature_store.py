"""
Feature Store.

Responsabilidades:
- Construir snapshots unificados de features para Binance Futures.
- Validar schema com Pydantic.
- Salvar snapshots no TimescaleDB.
- Preparar cache Redis do último snapshot por timeframe.
- Preservar campos opcionais para Polymarket no futuro.

Este módulo NÃO calcula indicadores.
Este módulo NÃO executa ordens.
Este módulo NÃO decide trade.
Ele apenas persiste features para backtest, auditoria e modelos.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "1d"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_to_utc_datetime(value: Any) -> datetime:
    """
    Aceita:
    - datetime
    - ISO string
    - Unix seconds
    - Unix milliseconds
    - None
    """
    if value is None:
        return utc_now()

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return utc_now()

        if stripped.isdigit():
            return timestamp_to_utc_datetime(int(stripped))

        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc)
        except ValueError:
            return utc_now()

    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return utc_now()

    if numeric >= 1_000_000_000_000:
        numeric = numeric // 1000

    return datetime.fromtimestamp(numeric, tz=timezone.utc)


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        if isinstance(value, float) and math.isnan(value):
            return None

        return float(value)
    except (TypeError, ValueError):
        return None


def clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def env_float(name: str, default: float) -> float:
    parsed = safe_float(os.getenv(name))

    if parsed is None:
        return default

    return parsed


def normalize_timeframe(value: str) -> str:
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

    normalized = mapping.get(value.strip())

    if normalized not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"timeframe inválido: {value}")

    return normalized


def normalize_symbol(value: str) -> str:
    value = value.strip().upper()

    if not value:
        raise ValueError("symbol não pode ser vazio")

    return value


def calculate_combined_score(
    *,
    tech_score: float,
    microstructure_score: float,
    onchain_score: float,
    sentiment_score: float,
) -> float:
    weight_technical = env_float("FEATURE_WEIGHT_TECHNICAL", 0.50)
    weight_microstructure = env_float("FEATURE_WEIGHT_MICROSTRUCTURE", 0.20)
    weight_onchain = env_float("FEATURE_WEIGHT_ONCHAIN", 0.15)
    weight_sentiment = env_float("FEATURE_WEIGHT_SENTIMENT", 0.15)

    total_weight = (
        weight_technical
        + weight_microstructure
        + weight_onchain
        + weight_sentiment
    )

    if total_weight <= 0:
        return 0.0

    raw_score = (
        tech_score * weight_technical
        + microstructure_score * weight_microstructure
        + onchain_score * weight_onchain
        + sentiment_score * weight_sentiment
    ) / total_weight

    return clamp(raw_score)


class FeatureSnapshot(BaseModel):
    """
    Snapshot unificado de features.

    Schema principal:
    timestamp, venue, instrument_id, symbol, timeframe,
    tech_score, onchain_score, sentiment_score, microstructure_score,
    combined_score, campos auxiliares e JSONs.
    """

    model_config = ConfigDict(extra="allow")

    timestamp: datetime = Field(default_factory=utc_now)

    venue: str = "binance_futures"
    instrument_id: str = "BTCUSDT"
    symbol: str = "BTCUSDT"
    timeframe: str

    # Opcional para Polymarket no futuro.
    market_id: str | None = None

    tech_score: float
    onchain_score: float = 0.0
    sentiment_score: float = 0.0
    microstructure_score: float = 0.0
    combined_score: float

    # Campos Polymarket opcionais.
    poly_spread: float | None = None
    poly_liquidity: float | None = None
    time_to_expiry_seconds: float | None = None

    # Campos Binance Futures.
    binance_spread_pct: float | None = None
    binance_liquidity_usd: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    mark_price: float | None = None
    index_price: float | None = None

    # Features ricas para modelos/backtest.
    btc_features: dict[str, Any] = Field(default_factory=dict)
    raw_components: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("timestamp", "created_at", mode="before")
    @classmethod
    def validate_datetime(cls, value: Any) -> datetime:
        return timestamp_to_utc_datetime(value)

    @field_validator("venue")
    @classmethod
    def validate_venue(cls, value: str) -> str:
        value = value.strip().lower()

        if not value:
            raise ValueError("venue não pode ser vazio")

        return value

    @field_validator("instrument_id", "symbol")
    @classmethod
    def validate_symbol_fields(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        return normalize_timeframe(value)

    @field_validator(
        "tech_score",
        "onchain_score",
        "sentiment_score",
        "microstructure_score",
        "combined_score",
    )
    @classmethod
    def validate_score_range(cls, value: float) -> float:
        if value < -1 or value > 1:
            raise ValueError("score deve estar entre -1 e +1")

        return float(value)


def unwrap_analysis(component: dict[str, Any] | None) -> dict[str, Any]:
    """
    Alguns eventos chegam como:
    {"analysis": {...}}

    Outros já são diretamente:
    {"spread_pct": ..., "microstructure_score": ...}
    """
    if not component:
        return {}

    analysis = component.get("analysis")

    if isinstance(analysis, dict):
        return analysis

    return component


def build_feature_snapshot(
    *,
    timeframe: str,
    technical: dict[str, Any],
    orderbook: dict[str, Any] | None = None,
    onchain: dict[str, Any] | None = None,
    sentiment: dict[str, Any] | None = None,
    venue: str = "binance_futures",
    symbol: str = "BTCUSDT",
    instrument_id: str | None = None,
    timestamp: Any = None,
    market_id: str | None = None,
) -> FeatureSnapshot:
    """
    Monta snapshot de features a partir das engines:
    - technical_engine
    - orderbook
    - onchain_engine
    - sentiment_engine
    """
    orderbook_payload = unwrap_analysis(orderbook)
    onchain_payload = onchain or {}
    sentiment_payload = sentiment or {}

    tech_score = safe_float(technical.get("technical_score")) or 0.0
    microstructure_score = safe_float(orderbook_payload.get("microstructure_score")) or 0.0
    onchain_score = safe_float(onchain_payload.get("onchain_score")) or 0.0
    sentiment_score = safe_float(sentiment_payload.get("sentiment_score")) or 0.0

    combined_score = calculate_combined_score(
        tech_score=tech_score,
        microstructure_score=microstructure_score,
        onchain_score=onchain_score,
        sentiment_score=sentiment_score,
    )

    indicators = technical.get("indicators") or {}

    bid_depth_notional = safe_float(orderbook_payload.get("bid_depth_notional"))
    ask_depth_notional = safe_float(orderbook_payload.get("ask_depth_notional"))

    if bid_depth_notional is not None and ask_depth_notional is not None:
        binance_liquidity_usd = min(bid_depth_notional, ask_depth_notional)
    else:
        binance_liquidity_usd = None

    btc_features = {
        "technical": technical,
        "orderbook": orderbook_payload,
        "onchain": onchain_payload,
        "sentiment": sentiment_payload,
    }

    return FeatureSnapshot(
        timestamp=timestamp or technical.get("latest_close_time") or technical.get("latest_open_time"),
        venue=venue,
        instrument_id=instrument_id or symbol,
        symbol=symbol,
        timeframe=timeframe,
        market_id=market_id,
        tech_score=clamp(tech_score),
        onchain_score=clamp(onchain_score),
        sentiment_score=clamp(sentiment_score),
        microstructure_score=clamp(microstructure_score),
        combined_score=combined_score,
        poly_spread=safe_float(orderbook_payload.get("poly_spread")),
        poly_liquidity=safe_float(orderbook_payload.get("poly_liquidity")),
        time_to_expiry_seconds=safe_float(orderbook_payload.get("time_to_expiry_seconds")),
        binance_spread_pct=safe_float(orderbook_payload.get("spread_pct")),
        binance_liquidity_usd=binance_liquidity_usd,
        funding_rate=safe_float(indicators.get("funding_rate") or technical.get("funding_rate")),
        open_interest=safe_float(indicators.get("open_interest") or technical.get("open_interest")),
        mark_price=safe_float(indicators.get("mark_price") or technical.get("mark_price")),
        index_price=safe_float(indicators.get("index_price") or technical.get("index_price")),
        btc_features=btc_features,
        raw_components={
            "technical": technical,
            "orderbook": orderbook,
            "onchain": onchain,
            "sentiment": sentiment,
        },
    )


def snapshot_to_record(snapshot: FeatureSnapshot) -> dict[str, Any]:
    payload = snapshot.model_dump(mode="python")

    # psycopg aceita datetime diretamente.
    payload["btc_features"] = json.dumps(snapshot.btc_features, ensure_ascii=False)
    payload["raw_components"] = json.dumps(snapshot.raw_components, ensure_ascii=False)

    return payload


def validate_sql_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"identificador SQL inválido: {value}")

    return value


def parse_table_name(value: str | None = None) -> tuple[str, str]:
    table_name = value or os.getenv("FEATURE_STORE_TABLE", "market_data.feature_snapshots")

    parts = table_name.split(".")

    if len(parts) == 1:
        return "public", validate_sql_identifier(parts[0])

    if len(parts) == 2:
        return validate_sql_identifier(parts[0]), validate_sql_identifier(parts[1])

    raise ValueError(f"FEATURE_STORE_TABLE inválido: {table_name}")


def qualified_table_name(value: str | None = None) -> str:
    schema, table = parse_table_name(value)

    return f"{schema}.{table}"


def build_create_table_sql(table_name: str | None = None) -> list[str]:
    schema, table = parse_table_name(table_name)
    full_table = f"{schema}.{table}"

    return [
        f"CREATE SCHEMA IF NOT EXISTS {schema};",
        f"""
        CREATE TABLE IF NOT EXISTS {full_table} (
            timestamp TIMESTAMPTZ NOT NULL,
            venue TEXT NOT NULL,
            instrument_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,

            market_id TEXT NULL,

            tech_score DOUBLE PRECISION NOT NULL,
            onchain_score DOUBLE PRECISION NOT NULL,
            sentiment_score DOUBLE PRECISION NOT NULL,
            microstructure_score DOUBLE PRECISION NOT NULL,
            combined_score DOUBLE PRECISION NOT NULL,

            poly_spread DOUBLE PRECISION NULL,
            poly_liquidity DOUBLE PRECISION NULL,
            time_to_expiry_seconds DOUBLE PRECISION NULL,

            binance_spread_pct DOUBLE PRECISION NULL,
            binance_liquidity_usd DOUBLE PRECISION NULL,
            funding_rate DOUBLE PRECISION NULL,
            open_interest DOUBLE PRECISION NULL,
            mark_price DOUBLE PRECISION NULL,
            index_price DOUBLE PRECISION NULL,

            btc_features JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            raw_components JSONB NOT NULL DEFAULT '{{}}'::jsonb,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            PRIMARY KEY (timestamp, venue, instrument_id, timeframe)
        );
        """,
        f"CREATE INDEX IF NOT EXISTS idx_{table}_symbol_tf_ts ON {full_table} (symbol, timeframe, timestamp DESC);",
        f"CREATE INDEX IF NOT EXISTS idx_{table}_venue_ts ON {full_table} (venue, timestamp DESC);",
    ]


def build_create_hypertable_sql(table_name: str | None = None) -> str:
    full_table = qualified_table_name(table_name)

    return (
        "SELECT create_hypertable("
        f"'{full_table}', "
        "'timestamp', "
        "if_not_exists => TRUE"
        ");"
    )


INSERT_COLUMNS = [
    "timestamp",
    "venue",
    "instrument_id",
    "symbol",
    "timeframe",
    "market_id",
    "tech_score",
    "onchain_score",
    "sentiment_score",
    "microstructure_score",
    "combined_score",
    "poly_spread",
    "poly_liquidity",
    "time_to_expiry_seconds",
    "binance_spread_pct",
    "binance_liquidity_usd",
    "funding_rate",
    "open_interest",
    "mark_price",
    "index_price",
    "btc_features",
    "raw_components",
    "created_at",
]


def build_insert_sql(table_name: str | None = None) -> str:
    full_table = qualified_table_name(table_name)

    columns = ", ".join(INSERT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(INSERT_COLUMNS))

    updates = ", ".join(
        [
            f"{column} = EXCLUDED.{column}"
            for column in INSERT_COLUMNS
            if column not in {"timestamp", "venue", "instrument_id", "timeframe"}
        ]
    )

    return f"""
    INSERT INTO {full_table} ({columns})
    VALUES ({placeholders})
    ON CONFLICT (timestamp, venue, instrument_id, timeframe)
    DO UPDATE SET {updates};
    """


def record_to_insert_values(record: dict[str, Any]) -> list[Any]:
    return [record.get(column) for column in INSERT_COLUMNS]


class TimescaleFeatureStore:
    """
    Writer simples para TimescaleDB.

    A importação de psycopg é feita apenas em runtime para os testes
    unitários não dependerem de banco nem driver instalado.
    """

    def __init__(
        self,
        *,
        database_url: str | None = None,
        table_name: str | None = None,
        create_hypertable: bool | None = None,
    ) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")

        if not self.database_url:
            raise ValueError("DATABASE_URL não configurada")

        self.table_name = table_name or os.getenv("FEATURE_STORE_TABLE", "market_data.feature_snapshots")

        self.create_hypertable = (
            create_hypertable
            if create_hypertable is not None
            else os.getenv("FEATURE_STORE_CREATE_HYPERTABLE", "true").lower() in {"1", "true", "yes", "on"}
        )

    def _connect(self):
        try:
            import psycopg  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "psycopg não está instalado. Adicione psycopg[binary] ao ambiente para gravar no TimescaleDB."
            ) from exc

        return psycopg.connect(self.database_url)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for statement in build_create_table_sql(self.table_name):
                    cursor.execute(statement)

                if self.create_hypertable:
                    try:
                        cursor.execute(build_create_hypertable_sql(self.table_name))
                    except Exception:
                        # Em desenvolvimento, Timescale pode não estar com extensão ativa.
                        # A tabela continua utilizável como PostgreSQL comum.
                        connection.rollback()

                        with connection.cursor() as retry_cursor:
                            for statement in build_create_table_sql(self.table_name):
                                retry_cursor.execute(statement)

                connection.commit()

    def insert_snapshot(self, snapshot: FeatureSnapshot) -> None:
        record = snapshot_to_record(snapshot)
        sql = build_insert_sql(self.table_name)
        values = record_to_insert_values(record)

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)

            connection.commit()

    def insert_many(self, snapshots: list[FeatureSnapshot]) -> None:
        if not snapshots:
            return

        sql = build_insert_sql(self.table_name)
        records = [snapshot_to_record(snapshot) for snapshot in snapshots]
        values = [record_to_insert_values(record) for record in records]

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(sql, values)

            connection.commit()