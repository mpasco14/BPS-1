"""
Binance Futures orderbook WebSocket connector.

Responsabilidades:
- Conectar ao WebSocket público da Binance USDⓈ-M Futures.
- Consumir partial book depth de BTCUSDT.
- Analisar microestrutura via strategy/orderbook.py.
- Publicar eventos analisados no Redpanda/Kafka no tópico binance-orderbook.
- Reconectar automaticamente em caso de queda.

Este módulo NÃO executa ordens.
Este módulo NÃO usa API key.
Este módulo NÃO faz trading real.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import websockets
from confluent_kafka import Producer
from dotenv import load_dotenv

from strategy.orderbook import analyze_orderbook, analysis_to_dict


load_dotenv()


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KafkaEvent:
    topic: str
    key: str
    value: dict[str, Any]


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("symbol não pode ser vazio")

    return symbol


def normalize_depth_levels(value: int | str) -> int:
    depth = int(value)

    if depth not in {5, 10, 20}:
        raise ValueError("depth_levels precisa ser 5, 10 ou 20")

    return depth


def normalize_update_speed(value: str | None) -> str:
    if value is None:
        return ""

    value = value.strip().lower()

    if value in {"", "250ms"}:
        return ""

    if value not in {"100ms", "500ms"}:
        raise ValueError("update_speed precisa ser 100ms, 500ms, 250ms ou vazio")

    return value


def build_orderbook_stream_name(
    *,
    symbol: str,
    depth_levels: int,
    update_speed: str | None = None,
) -> str:
    clean_symbol = normalize_symbol(symbol).lower()
    clean_depth = normalize_depth_levels(depth_levels)
    clean_speed = normalize_update_speed(update_speed)

    stream = f"{clean_symbol}@depth{clean_depth}"

    if clean_speed:
        stream = f"{stream}@{clean_speed}"

    return stream


def build_orderbook_ws_url(
    *,
    base_url: str,
    symbol: str,
    depth_levels: int,
    update_speed: str | None = None,
) -> str:
    """
    Usa modo /ws/<streamName> no endpoint público.

    Exemplo:
    wss://fstream.binance.com/public/ws/btcusdt@depth5@100ms
    """
    clean_base_url = base_url.rstrip("/")
    stream = build_orderbook_stream_name(
        symbol=symbol,
        depth_levels=depth_levels,
        update_speed=update_speed,
    )

    return f"{clean_base_url}/ws/{stream}"


def unwrap_stream_message(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Suporta tanto mensagem direta quanto combined stream.

    Direct:
      {"e": "depthUpdate", "b": [...], "a": [...]}

    Combined:
      {"stream": "...", "data": {"e": "depthUpdate", ...}}
    """
    data = payload.get("data")

    if isinstance(data, dict):
        return data

    return payload


def normalize_orderbook_ws_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = unwrap_stream_message(payload)

    symbol = data.get("s") or data.get("symbol") or os.getenv("BINANCE_FUTURES_ORDERBOOK_SYMBOL", "BTCUSDT")

    return {
        "source": "binance_orderbook_ws",
        "venue": "binance_futures",
        "symbol": str(symbol).upper(),
        "event_type": data.get("e", "depthUpdate"),
        "event_time": data.get("E"),
        "transaction_time": data.get("T"),
        "first_update_id": data.get("U"),
        "final_update_id": data.get("u"),
        "previous_final_update_id": data.get("pu"),
        "b": data.get("b", data.get("bids", [])),
        "a": data.get("a", data.get("asks", [])),
        "raw": data,
    }


def orderbook_analysis_to_kafka(
    *,
    analysis: dict[str, Any],
    raw_event: dict[str, Any],
    topic: str,
) -> KafkaEvent:
    symbol = str(analysis.get("symbol") or raw_event.get("symbol") or "BTCUSDT")
    event_time = raw_event.get("event_time") or raw_event.get("transaction_time") or "unknown"
    final_update_id = raw_event.get("final_update_id") or "unknown"

    key = f"{symbol}:orderbook:{event_time}:{final_update_id}"

    value = {
        "source": "binance_orderbook_ws",
        "event_type": "orderbook_microstructure",
        "venue": "binance_futures",
        "symbol": symbol,
        "event_time": raw_event.get("event_time"),
        "transaction_time": raw_event.get("transaction_time"),
        "first_update_id": raw_event.get("first_update_id"),
        "final_update_id": raw_event.get("final_update_id"),
        "previous_final_update_id": raw_event.get("previous_final_update_id"),
        "analysis": analysis,
        "raw": raw_event,
    }

    return KafkaEvent(
        topic=topic,
        key=key,
        value=value,
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
                "client.id": "btc-polymarket-bot-binance-orderbook-ws",
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


class BinanceOrderbookWsConnector:
    def __init__(
        self,
        *,
        producer: KafkaJsonProducer | None = None,
        symbol: str | None = None,
        depth_levels: int | None = None,
        update_speed: str | None = None,
        publish_to_kafka: bool | None = None,
    ) -> None:
        self.producer = producer or KafkaJsonProducer()

        self.symbol = normalize_symbol(
            symbol or os.getenv("BINANCE_FUTURES_ORDERBOOK_SYMBOL", "BTCUSDT")
        )

        self.depth_levels = normalize_depth_levels(
            depth_levels or os.getenv("BINANCE_FUTURES_ORDERBOOK_DEPTH_LEVELS", "5")
        )

        self.update_speed = normalize_update_speed(
            update_speed or os.getenv("BINANCE_FUTURES_ORDERBOOK_UPDATE_SPEED", "100ms")
        )

        self.base_url = os.getenv(
            "BINANCE_FUTURES_ORDERBOOK_WS_BASE_URL",
            "wss://fstream.binance.com/public",
        )

        self.topic = os.getenv("BINANCE_ORDERBOOK_TOPIC", "binance-orderbook")

        self.publish_to_kafka = (
            publish_to_kafka
            if publish_to_kafka is not None
            else parse_bool(os.getenv("BINANCE_FUTURES_ORDERBOOK_PUBLISH_TO_KAFKA"), default=True)
        )

        self.reconnect_initial_seconds = float(
            os.getenv("BINANCE_FUTURES_ORDERBOOK_RECONNECT_INITIAL_SECONDS", "2")
        )

        self.reconnect_max_seconds = float(
            os.getenv("BINANCE_FUTURES_ORDERBOOK_RECONNECT_MAX_SECONDS", "60")
        )

        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def ws_url(self) -> str:
        return build_orderbook_ws_url(
            base_url=self.base_url,
            symbol=self.symbol,
            depth_levels=self.depth_levels,
            update_speed=self.update_speed,
        )

    async def run(self) -> None:
        enabled = parse_bool(os.getenv("BINANCE_FUTURES_ORDERBOOK_WS_ENABLED"), default=True)

        if not enabled:
            logger.warning("Binance orderbook WS disabled.")
            return

        reconnect_delay = self.reconnect_initial_seconds

        while not self._stop_event.is_set():
            try:
                await self._connect_and_consume()
                reconnect_delay = self.reconnect_initial_seconds
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Binance orderbook WebSocket error: %s", exc)

            if self._stop_event.is_set():
                break

            logger.info("Reconnecting Binance orderbook WS in %.1f seconds", reconnect_delay)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, self.reconnect_max_seconds)

    async def _connect_and_consume(self) -> None:
        url = self.ws_url()

        logger.info("Connecting Binance orderbook WebSocket: %s", url)

        async with websockets.connect(url, ping_interval=None) as websocket:
            async for raw_message in websocket:
                if self._stop_event.is_set():
                    break

                await self._handle_raw_message(raw_message)

    async def _handle_raw_message(self, raw_message: Any) -> dict[str, Any] | None:
        if not isinstance(raw_message, str):
            logger.debug("Ignoring non-string orderbook message: %r", raw_message)
            return None

        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.warning("Could not decode orderbook WS message: %s", raw_message[:500])
            return None

        event = normalize_orderbook_ws_payload(payload)

        analysis = analyze_orderbook(
            raw=event,
            symbol=event["symbol"],
            depth_levels=self.depth_levels,
        )

        analysis_payload = analysis_to_dict(analysis)

        if self.publish_to_kafka:
            kafka_event = orderbook_analysis_to_kafka(
                analysis=analysis_payload,
                raw_event=event,
                topic=self.topic,
            )

            self.producer.publish(kafka_event)

        logger.info(
            "Orderbook symbol=%s spread_pct=%s score=%s tradeable=%s blockers=%s",
            analysis.symbol,
            analysis.spread_pct,
            analysis.microstructure_score,
            analysis.is_tradeable,
            analysis.blockers,
        )

        return analysis_payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Binance Futures orderbook WebSocket connector")

    parser.add_argument(
        "--symbol",
        default=os.getenv("BINANCE_FUTURES_ORDERBOOK_SYMBOL", "BTCUSDT"),
        help="Futures symbol, e.g. BTCUSDT",
    )

    parser.add_argument(
        "--depth-levels",
        type=int,
        default=int(os.getenv("BINANCE_FUTURES_ORDERBOOK_DEPTH_LEVELS", "5")),
        help="Partial book depth levels: 5, 10 or 20",
    )

    parser.add_argument(
        "--update-speed",
        default=os.getenv("BINANCE_FUTURES_ORDERBOOK_UPDATE_SPEED", "100ms"),
        help="Update speed: 100ms, 500ms, 250ms or empty",
    )

    parser.add_argument(
        "--run-seconds",
        type=float,
        default=float(os.getenv("BINANCE_FUTURES_ORDERBOOK_RUN_SECONDS", "60")),
        help="How long to run before stopping. 0 means forever.",
    )

    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Do not publish to Kafka/Redpanda",
    )

    return parser


async def async_main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    connector = BinanceOrderbookWsConnector(
        symbol=args.symbol,
        depth_levels=args.depth_levels,
        update_speed=args.update_speed,
        publish_to_kafka=not args.no_publish,
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

    connector.producer.flush()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()