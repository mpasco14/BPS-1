"""
Candle Store.

Responsabilidades:
- Consumir eventos do tópico Kafka/Redpanda btc-candles.
- Validar schema dos candles BTC.
- Gravar o candle mais recente no Redis.
- Preparar registro para futura gravação no TimescaleDB.

Este módulo NÃO coleta dados diretamente da Binance.
Ele consome dados já publicados por connectors/binance_ws.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from typing import Any

import redis
from confluent_kafka import Consumer, KafkaException, Message
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


load_dotenv()


logger = logging.getLogger(__name__)


class CandleEvent(BaseModel):
    """
    Schema validado do candle produzido por connectors/binance_ws.py.
    """

    model_config = ConfigDict(extra="allow")

    source: str
    exchange: str
    market_type: str

    symbol: str
    timeframe: str

    open_time: int
    close_time: int
    event_time: int | None = None

    open: float
    high: float
    low: float
    close: float
    volume: float

    quote_volume: float | None = None
    trades_count: int | None = None
    taker_buy_base_volume: float | None = None
    taker_buy_quote_volume: float | None = None

    is_closed: bool

    funding_rate: float | None = None
    funding_time: int | None = None
    open_interest: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    next_funding_time: int | None = None
    metrics_collected_at: str | None = None

    received_at: str
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

        allowed = {"5m", "15m", "1h", "1d"}

        if value not in allowed:
            raise ValueError(f"timeframe inválido: {value}")

        return value

    @field_validator("high")
    @classmethod
    def high_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("high precisa ser maior que zero")

        return value

    @field_validator("low")
    @classmethod
    def low_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("low precisa ser maior que zero")

        return value

    @field_validator("open", "close")
    @classmethod
    def price_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("preço precisa ser maior que zero")

        return value

    @field_validator("volume")
    @classmethod
    def volume_must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("volume não pode ser negativo")

        return value


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_message_value(value: bytes | str | dict[str, Any]) -> dict[str, Any]:
    """
    Converte valor vindo do Kafka em dict.

    Pode receber:
    - bytes
    - string JSON
    - dict
    """
    if isinstance(value, dict):
        return value

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    if isinstance(value, str):
        payload = json.loads(value)

        if not isinstance(payload, dict):
            raise ValueError("Mensagem Kafka não contém um JSON object")

        return payload

    raise TypeError(f"Tipo de mensagem não suportado: {type(value)!r}")


def validate_candle_event(payload: dict[str, Any]) -> CandleEvent:
    """
    Valida o payload usando Pydantic.
    """
    return CandleEvent.model_validate(payload)


def build_candle_redis_key(
    *,
    symbol: str,
    timeframe: str,
    prefix: str | None = None,
    environment: str | None = None,
) -> str:
    """
    Monta chave oficial do Redis:

    btc_poly_bot:dev:btc_candle:{symbol}:{timeframe}
    """
    redis_prefix = prefix or os.getenv("REDIS_KEY_PREFIX", "btc_poly_bot")
    redis_env = environment or os.getenv("REDIS_KEY_ENV", "dev")

    return f"{redis_prefix}:{redis_env}:btc_candle:{symbol.upper()}:{timeframe}"


def candle_to_redis_json(candle: CandleEvent) -> str:
    """
    Serializa candle para JSON antes de gravar no Redis.
    """
    return json.dumps(
        candle.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def candle_to_timescale_row(candle: CandleEvent) -> dict[str, Any]:
    """
    Prepara registro para futura gravação no TimescaleDB.

    Nesta etapa ainda não fazemos INSERT.
    Esta função existe para já padronizar os campos.
    """
    return {
        "symbol": candle.symbol,
        "timeframe": candle.timeframe,
        "open_time": candle.open_time,
        "close_time": candle.close_time,
        "event_time": candle.event_time,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "quote_volume": candle.quote_volume,
        "trades_count": candle.trades_count,
        "taker_buy_base_volume": candle.taker_buy_base_volume,
        "taker_buy_quote_volume": candle.taker_buy_quote_volume,
        "is_closed": candle.is_closed,
        "funding_rate": candle.funding_rate,
        "funding_time": candle.funding_time,
        "open_interest": candle.open_interest,
        "mark_price": candle.mark_price,
        "index_price": candle.index_price,
        "next_funding_time": candle.next_funding_time,
        "metrics_collected_at": candle.metrics_collected_at,
        "received_at": candle.received_at,
        "raw": candle.raw,
    }


class RedisCandleStore:
    """
    Store de candles recentes no Redis.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self.redis_url = redis_url or os.getenv(
            "REDIS_URL",
            "redis://:redis_password_dev@localhost:6379/0",
        )

        self.ttl_seconds = int(
            ttl_seconds
            or os.getenv("CANDLE_STORE_REDIS_TTL_SECONDS", "900")
        )

        self.client = redis.Redis.from_url(
            self.redis_url,
            decode_responses=True,
        )

    def write_latest(self, candle: CandleEvent) -> str:
        key = build_candle_redis_key(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
        )

        value = candle_to_redis_json(candle)

        self.client.setex(
            key,
            self.ttl_seconds,
            value,
        )

        return key


class CandleStoreService:
    """
    Serviço principal de processamento de mensagens.
    """

    def __init__(
        self,
        *,
        redis_store: RedisCandleStore | Any,
        write_redis: bool = True,
        write_timescale: bool = False,
    ) -> None:
        self.redis_store = redis_store
        self.write_redis = write_redis
        self.write_timescale = write_timescale

    def process_message_value(self, value: bytes | str | dict[str, Any]) -> CandleEvent:
        payload = parse_message_value(value)
        candle = validate_candle_event(payload)

        if self.write_redis:
            key = self.redis_store.write_latest(candle)

            logger.info(
                "Wrote latest candle to Redis key=%s symbol=%s timeframe=%s close=%s",
                key,
                candle.symbol,
                candle.timeframe,
                candle.close,
            )

        if self.write_timescale:
            row = candle_to_timescale_row(candle)

            # A gravação real no TimescaleDB será implementada em etapa futura.
            logger.info(
                "Prepared TimescaleDB candle row symbol=%s timeframe=%s open_time=%s",
                row["symbol"],
                row["timeframe"],
                row["open_time"],
            )

        return candle


class CandleKafkaConsumer:
    """
    Consumer Kafka/Redpanda do tópico btc-candles.
    """

    def __init__(
        self,
        *,
        service: CandleStoreService,
        topic: str,
        group_id: str,
        bootstrap_servers: str,
    ) -> None:
        self.service = service
        self.topic = topic
        self.consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": "latest",
                "enable.auto.commit": False,
                "client.id": "btc-polymarket-bot-candle-store",
            }
        )

    def run(self, run_seconds: float = 0) -> None:
        self.consumer.subscribe([self.topic])

        logger.info("Subscribed to Kafka topic=%s", self.topic)

        started_at = time.monotonic()

        try:
            while True:
                if run_seconds > 0 and time.monotonic() - started_at >= run_seconds:
                    logger.info("Run seconds reached. Stopping candle store.")
                    break

                message = self.consumer.poll(1.0)

                if message is None:
                    continue

                if message.error():
                    raise KafkaException(message.error())

                self._handle_message(message)

        finally:
            self.consumer.close()

    def _handle_message(self, message: Message) -> None:
        try:
            candle = self.service.process_message_value(message.value())
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.exception("Invalid candle message skipped: %s", exc)
            return

        self.consumer.commit(message=message, asynchronous=False)

        logger.info(
            "Committed candle message topic=%s partition=%s offset=%s symbol=%s timeframe=%s",
            message.topic(),
            message.partition(),
            message.offset(),
            candle.symbol,
            candle.timeframe,
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Candle Store consumer")

    parser.add_argument(
        "--run-seconds",
        type=float,
        default=float(os.getenv("CANDLE_STORE_RUN_SECONDS", "60")),
        help="How long to run before stopping. 0 means forever.",
    )

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    enabled = parse_bool(os.getenv("CANDLE_STORE_ENABLED"), default=True)

    if not enabled:
        logger.warning("Candle Store disabled by CANDLE_STORE_ENABLED=false")
        return

    topic = os.getenv("CANDLE_STORE_TOPIC", "btc-candles")
    group_id = os.getenv("CANDLE_STORE_CONSUMER_GROUP", "candle-store")
    bootstrap_servers = (
        os.getenv("REDPANDA_BOOTSTRAP_SERVERS")
        or os.getenv("KAFKA_BOOTSTRAP_SERVERS")
        or "localhost:19092"
    )

    write_redis = parse_bool(os.getenv("CANDLE_STORE_WRITE_REDIS"), default=True)
    write_timescale = parse_bool(os.getenv("CANDLE_STORE_WRITE_TIMESCALE"), default=False)

    redis_store = RedisCandleStore()

    service = CandleStoreService(
        redis_store=redis_store,
        write_redis=write_redis,
        write_timescale=write_timescale,
    )

    consumer = CandleKafkaConsumer(
        service=service,
        topic=topic,
        group_id=group_id,
        bootstrap_servers=bootstrap_servers,
    )

    consumer.run(run_seconds=args.run_seconds)


if __name__ == "__main__":
    main()