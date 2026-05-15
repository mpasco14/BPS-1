"""
Binance Futures WebSocket connector.

Responsabilidades:
- Conectar ao WebSocket público da Binance USDⓈ-M Futures.
- Consumir candles BTCUSDT nos timeframes 5m, 15m, 1h e 1d.
- Capturar OHLCV, quote volume, trades_count e taker volumes.
- Coletar métricas REST complementares:
  - funding rate
  - open interest
  - mark price
  - index price
- Publicar eventos normalizados no Redpanda/Kafka no tópico btc-candles.

Este módulo NÃO executa ordens.
Este módulo NÃO usa chave privada.
Este módulo NÃO faz trading real.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import websockets
from confluent_kafka import Producer
from dotenv import load_dotenv


load_dotenv()


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BinanceFuturesMetrics:
    symbol: str
    funding_rate: float | None
    funding_time: int | None
    open_interest: float | None
    mark_price: float | None
    index_price: float | None
    next_funding_time: int | None
    collected_at: str


@dataclass(frozen=True)
class BinanceCandleEvent:
    source: str
    exchange: str
    market_type: str
    symbol: str
    timeframe: str

    open_time: int
    close_time: int
    event_time: int | None

    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float | None
    trades_count: int | None
    taker_buy_base_volume: float | None
    taker_buy_quote_volume: float | None

    is_closed: bool

    funding_rate: float | None
    funding_time: int | None
    open_interest: float | None
    mark_price: float | None
    index_price: float | None
    next_funding_time: int | None
    metrics_collected_at: str | None

    received_at: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class KafkaEvent:
    topic: str
    key: str
    value: dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []

    return [item.strip() for item in value.split(",") if item.strip()]


def str_to_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def str_to_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_combined_stream_url(
    *,
    base_url: str,
    symbol: str,
    intervals: list[str],
) -> str:
    """
    Monta URL combinada para streams de kline.

    Exemplo:
    wss://fstream.binance.com/market/stream?streams=btcusdt@kline_5m/btcusdt@kline_15m
    """
    clean_base_url = base_url.rstrip("/")
    lower_symbol = symbol.lower()

    streams = "/".join(
        f"{lower_symbol}@kline_{interval}"
        for interval in intervals
    )

    return f"{clean_base_url}/stream?streams={streams}"


def unwrap_combined_stream_message(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Streams combinados da Binance chegam como:

    {
      "stream": "btcusdt@kline_5m",
      "data": {...}
    }

    Esta função retorna payload["data"] quando existir.
    """
    data = payload.get("data")

    if isinstance(data, dict):
        return data

    return payload


def normalize_kline_message(
    payload: dict[str, Any],
    metrics: BinanceFuturesMetrics | None = None,
) -> BinanceCandleEvent | None:
    """
    Normaliza payload de kline da Binance.

    Campos principais:
    - e: event type
    - E: event time
    - s: symbol
    - k: kline payload
    """
    message = unwrap_combined_stream_message(payload)

    if message.get("e") != "kline":
        return None

    kline = message.get("k")

    if not isinstance(kline, dict):
        return None

    symbol = str(kline.get("s") or message.get("s") or "").upper()
    timeframe = str(kline.get("i") or "")

    open_price = str_to_float(kline.get("o"))
    high_price = str_to_float(kline.get("h"))
    low_price = str_to_float(kline.get("l"))
    close_price = str_to_float(kline.get("c"))
    volume = str_to_float(kline.get("v"))

    if (
        not symbol
        or not timeframe
        or open_price is None
        or high_price is None
        or low_price is None
        or close_price is None
        or volume is None
    ):
        return None

    return BinanceCandleEvent(
        source="binance_ws",
        exchange="binance",
        market_type="usds_m_futures",
        symbol=symbol,
        timeframe=timeframe,
        open_time=int(kline.get("t")),
        close_time=int(kline.get("T")),
        event_time=str_to_int(message.get("E")),
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        quote_volume=str_to_float(kline.get("q")),
        trades_count=str_to_int(kline.get("n")),
        taker_buy_base_volume=str_to_float(kline.get("V")),
        taker_buy_quote_volume=str_to_float(kline.get("Q")),
        is_closed=bool(kline.get("x")),
        funding_rate=metrics.funding_rate if metrics else None,
        funding_time=metrics.funding_time if metrics else None,
        open_interest=metrics.open_interest if metrics else None,
        mark_price=metrics.mark_price if metrics else None,
        index_price=metrics.index_price if metrics else None,
        next_funding_time=metrics.next_funding_time if metrics else None,
        metrics_collected_at=metrics.collected_at if metrics else None,
        received_at=utc_now_iso(),
        raw=message,
    )


def candle_event_to_kafka(event: BinanceCandleEvent, topic: str) -> KafkaEvent:
    key = f"{event.symbol}:{event.timeframe}:{event.open_time}"

    return KafkaEvent(
        topic=topic,
        key=key,
        value=asdict(event),
    )


class KafkaJsonProducer:
    def __init__(self, bootstrap_servers: str | None = None) -> None:
        self.bootstrap_servers = (
            bootstrap_servers
            or os.getenv("REDPANDA_BOOTSTRAP_SERVERS")
            or os.getenv("KAFKA_BOOTSTRAP_SERVERS")
            or "localhost:19092"
        )

        self.producer = Producer(
            {
                "bootstrap.servers": self.bootstrap_servers,
                "client.id": "btc-polymarket-bot-binance-ws",
                "acks": "all",
                "enable.idempotence": True,
            }
        )

    def publish(self, event: KafkaEvent) -> None:
        payload = json.dumps(event.value, ensure_ascii=False).encode("utf-8")

        self.producer.produce(
            topic=event.topic,
            key=event.key.encode("utf-8"),
            value=payload,
            callback=self._delivery_report,
        )

        self.producer.poll(0)

    def flush(self) -> None:
        self.producer.flush()

    @staticmethod
    def _delivery_report(error: Any, message: Any) -> None:
        if error is not None:
            logger.error("Kafka delivery failed: %s", error)
            return

        logger.debug(
            "Kafka delivered topic=%s partition=%s offset=%s",
            message.topic(),
            message.partition(),
            message.offset(),
        )


class BinanceFuturesRestClient:
    def __init__(self) -> None:
        self.base_url = os.getenv(
            "BINANCE_FUTURES_REST_URL",
            "https://fapi.binance.com",
        ).rstrip("/")

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=15,
            headers={
                "Accept": "application/json",
                "User-Agent": "btc-polymarket-bot/0.1",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch_latest_funding_rate(self, symbol: str) -> tuple[float | None, int | None]:
        response = await self.client.get(
            "/fapi/v1/fundingRate",
            params={
                "symbol": symbol,
                "limit": 1,
            },
        )
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, list) or not payload:
            return None, None

        latest = payload[-1]

        return (
            str_to_float(latest.get("fundingRate")),
            str_to_int(latest.get("fundingTime")),
        )

    async def fetch_open_interest(self, symbol: str) -> float | None:
        response = await self.client.get(
            "/fapi/v1/openInterest",
            params={"symbol": symbol},
        )
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            return None

        return str_to_float(payload.get("openInterest"))

    async def fetch_mark_price_payload(self, symbol: str) -> dict[str, Any]:
        response = await self.client.get(
            "/fapi/v1/premiumIndex",
            params={"symbol": symbol},
        )
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            return {}

        return payload

    async def fetch_metrics(self, symbol: str) -> BinanceFuturesMetrics:
        funding_rate, funding_time = await self.fetch_latest_funding_rate(symbol)
        open_interest = await self.fetch_open_interest(symbol)
        mark_payload = await self.fetch_mark_price_payload(symbol)

        # premiumIndex também traz lastFundingRate. Se fundingRate histórico falhar,
        # usamos lastFundingRate como fallback.
        if funding_rate is None:
            funding_rate = str_to_float(mark_payload.get("lastFundingRate"))

        return BinanceFuturesMetrics(
            symbol=symbol,
            funding_rate=funding_rate,
            funding_time=funding_time,
            open_interest=open_interest,
            mark_price=str_to_float(mark_payload.get("markPrice")),
            index_price=str_to_float(mark_payload.get("indexPrice")),
            next_funding_time=str_to_int(mark_payload.get("nextFundingTime")),
            collected_at=utc_now_iso(),
        )


class BinanceWsConnector:
    def __init__(
        self,
        *,
        producer: KafkaJsonProducer,
        symbol: str,
        intervals: list[str],
    ) -> None:
        self.producer = producer
        self.symbol = symbol.upper()
        self.intervals = intervals

        self.ws_base_url = os.getenv(
            "BINANCE_FUTURES_WS_BASE_URL",
            "wss://fstream.binance.com/market",
        )

        self.topic = os.getenv("BINANCE_CANDLES_TOPIC", "btc-candles")

        self.publish_only_closed_klines = (
            os.getenv("BINANCE_PUBLISH_ONLY_CLOSED_KLINES", "true").lower() == "true"
        )

        self.metrics_refresh_seconds = float(
            os.getenv("BINANCE_FUTURES_METRICS_REFRESH_SECONDS", "30")
        )

        self._stop_event = asyncio.Event()
        self._latest_metrics: BinanceFuturesMetrics | None = None

    def stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        rest_client = BinanceFuturesRestClient()

        metrics_task = asyncio.create_task(
            self._metrics_refresh_loop(rest_client)
        )

        ws_task = asyncio.create_task(
            self._websocket_loop()
        )

        try:
            await asyncio.gather(metrics_task, ws_task)
        finally:
            metrics_task.cancel()
            ws_task.cancel()
            await rest_client.close()

    async def _metrics_refresh_loop(self, rest_client: BinanceFuturesRestClient) -> None:
        while not self._stop_event.is_set():
            try:
                self._latest_metrics = await rest_client.fetch_metrics(self.symbol)

                logger.info(
                    "Fetched Binance futures metrics symbol=%s funding_rate=%s open_interest=%s mark_price=%s",
                    self.symbol,
                    self._latest_metrics.funding_rate,
                    self._latest_metrics.open_interest,
                    self._latest_metrics.mark_price,
                )
            except Exception as exc:
                logger.exception("Failed to fetch Binance futures metrics: %s", exc)

            await asyncio.sleep(self.metrics_refresh_seconds)

    async def _websocket_loop(self) -> None:
        reconnect_delay = 2.0

        while not self._stop_event.is_set():
            try:
                await self._connect_and_consume()
                reconnect_delay = 2.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Binance WebSocket error: %s", exc)

            if self._stop_event.is_set():
                break

            logger.info("Reconnecting Binance WebSocket in %.1f seconds", reconnect_delay)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60.0)

    async def _connect_and_consume(self) -> None:
        ws_url = build_combined_stream_url(
            base_url=self.ws_base_url,
            symbol=self.symbol,
            intervals=self.intervals,
        )

        logger.info("Connecting Binance WebSocket: %s", ws_url)

        async with websockets.connect(ws_url, ping_interval=None) as websocket:
            async for raw_message in websocket:
                if self._stop_event.is_set():
                    break

                await self._handle_raw_message(raw_message)

    async def _handle_raw_message(self, raw_message: Any) -> None:
        if not isinstance(raw_message, str):
            logger.debug("Ignoring non-string Binance WS message: %r", raw_message)
            return

        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.warning("Could not decode Binance WS message: %s", raw_message[:500])
            return

        candle = normalize_kline_message(payload, metrics=self._latest_metrics)

        if candle is None:
            return

        if self.publish_only_closed_klines and not candle.is_closed:
            logger.debug(
                "Skipping open kline symbol=%s timeframe=%s open_time=%s",
                candle.symbol,
                candle.timeframe,
                candle.open_time,
            )
            return

        kafka_event = candle_event_to_kafka(candle, topic=self.topic)
        self.producer.publish(kafka_event)

        logger.info(
            "Published Binance candle symbol=%s timeframe=%s close=%s closed=%s topic=%s",
            candle.symbol,
            candle.timeframe,
            candle.close,
            candle.is_closed,
            self.topic,
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Binance Futures WebSocket candle connector")

    parser.add_argument(
        "--symbol",
        default=os.getenv("BINANCE_FUTURES_SYMBOL", "BTCUSDT"),
        help="Futures symbol, e.g. BTCUSDT",
    )

    parser.add_argument(
        "--intervals",
        default=os.getenv("BINANCE_KLINE_INTERVALS", "5m,15m,1h,1d"),
        help="Comma-separated kline intervals",
    )

    parser.add_argument(
        "--run-seconds",
        type=float,
        default=float(os.getenv("BINANCE_WS_RUN_SECONDS", "60")),
        help="How long to run before stopping. 0 means forever.",
    )

    return parser


async def async_main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    intervals = parse_csv_env(args.intervals)

    if not intervals:
        raise ValueError("At least one Binance kline interval is required.")

    producer = KafkaJsonProducer()

    connector = BinanceWsConnector(
        producer=producer,
        symbol=args.symbol,
        intervals=intervals,
    )

    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, connector.stop)
        except NotImplementedError:
            # Windows pode não suportar add_signal_handler para todos os sinais.
            pass

    run_task = asyncio.create_task(connector.run())

    if args.run_seconds > 0:
        try:
            await asyncio.wait_for(run_task, timeout=args.run_seconds)
        except asyncio.TimeoutError:
            logger.info("Run seconds reached. Stopping connector.")
            connector.stop()
            run_task.cancel()

            try:
                await run_task
            except asyncio.CancelledError:
                pass
    else:
        await run_task

    producer.flush()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()