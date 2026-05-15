"""
Polymarket WebSocket connector.

Responsabilidades:
- Conectar ao canal público "market" da Polymarket.
- Receber eventos de order book em tempo real.
- Publicar eventos normalizados no Kafka/Redpanda no tópico poly-orderbook.
- Preparar suporte ao canal "user" para fills e atividade de ordens.
- Reconectar automaticamente em caso de queda.

Este módulo NÃO executa ordens.
Este módulo NÃO assina transações.
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

import websockets
from confluent_kafka import Producer
from dotenv import load_dotenv


load_dotenv()


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KafkaEvent:
    topic: str
    key: str
    value: dict[str, Any]


@dataclass(frozen=True)
class NormalizedMarketWsEvent:
    source: str
    channel: str
    event_type: str
    market: str | None
    asset_id: str | None
    timestamp: str | None
    received_at: str
    raw: dict[str, Any]
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None


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


def calculate_best_bid_from_levels(levels: Any) -> float | None:
    if not isinstance(levels, list) or not levels:
        return None

    prices: list[float] = []

    for level in levels:
        if not isinstance(level, dict):
            continue

        price = str_to_float(level.get("price"))

        if price is not None:
            prices.append(price)

    if not prices:
        return None

    return max(prices)


def calculate_best_ask_from_levels(levels: Any) -> float | None:
    if not isinstance(levels, list) or not levels:
        return None

    prices: list[float] = []

    for level in levels:
        if not isinstance(level, dict):
            continue

        price = str_to_float(level.get("price"))

        if price is not None:
            prices.append(price)

    if not prices:
        return None

    return min(prices)


def calculate_spread(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None

    return round(best_ask - best_bid, 10)


def normalize_market_ws_message(message: dict[str, Any]) -> list[NormalizedMarketWsEvent]:
    """
    Normaliza mensagens do market channel.

    Eventos possíveis:
    - book
    - price_change
    - best_bid_ask
    - last_trade_price
    - tick_size_change
    - new_market
    - market_resolved

    Para price_change, uma mensagem pode conter vários price_changes.
    Nesse caso retornamos um evento normalizado por asset_id.
    """
    event_type = str(message.get("event_type") or message.get("type") or "unknown")
    received_at = utc_now_iso()

    normalized_events: list[NormalizedMarketWsEvent] = []

    if event_type == "book":
        bids = message.get("bids")
        asks = message.get("asks")

        best_bid = calculate_best_bid_from_levels(bids)
        best_ask = calculate_best_ask_from_levels(asks)
        spread = calculate_spread(best_bid, best_ask)

        normalized_events.append(
            NormalizedMarketWsEvent(
                source="polymarket_ws",
                channel="market",
                event_type=event_type,
                market=message.get("market"),
                asset_id=message.get("asset_id"),
                timestamp=message.get("timestamp"),
                received_at=received_at,
                raw=message,
                best_bid=best_bid,
                best_ask=best_ask,
                spread=spread,
            )
        )

        return normalized_events

    if event_type == "price_change":
        price_changes = message.get("price_changes")

        if not isinstance(price_changes, list):
            price_changes = []

        for price_change in price_changes:
            if not isinstance(price_change, dict):
                continue

            best_bid = str_to_float(price_change.get("best_bid"))
            best_ask = str_to_float(price_change.get("best_ask"))
            spread = calculate_spread(best_bid, best_ask)

            normalized_events.append(
                NormalizedMarketWsEvent(
                    source="polymarket_ws",
                    channel="market",
                    event_type=event_type,
                    market=message.get("market"),
                    asset_id=price_change.get("asset_id"),
                    timestamp=message.get("timestamp"),
                    received_at=received_at,
                    raw={
                        **message,
                        "price_change": price_change,
                    },
                    best_bid=best_bid,
                    best_ask=best_ask,
                    spread=spread,
                )
            )

        return normalized_events

    if event_type == "best_bid_ask":
        best_bid = str_to_float(message.get("best_bid"))
        best_ask = str_to_float(message.get("best_ask"))
        spread = str_to_float(message.get("spread"))

        if spread is None:
            spread = calculate_spread(best_bid, best_ask)

        normalized_events.append(
            NormalizedMarketWsEvent(
                source="polymarket_ws",
                channel="market",
                event_type=event_type,
                market=message.get("market"),
                asset_id=message.get("asset_id"),
                timestamp=message.get("timestamp"),
                received_at=received_at,
                raw=message,
                best_bid=best_bid,
                best_ask=best_ask,
                spread=spread,
            )
        )

        return normalized_events

    normalized_events.append(
        NormalizedMarketWsEvent(
            source="polymarket_ws",
            channel="market",
            event_type=event_type,
            market=message.get("market") or message.get("condition_id"),
            asset_id=message.get("asset_id"),
            timestamp=message.get("timestamp"),
            received_at=received_at,
            raw=message,
        )
    )

    return normalized_events


def normalized_market_event_to_kafka(
    event: NormalizedMarketWsEvent,
    topic: str,
) -> KafkaEvent:
    key_parts = [
        event.market or "unknown_market",
        event.asset_id or "unknown_asset",
        event.event_type,
    ]

    key = ":".join(key_parts)

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
                "client.id": "btc-polymarket-bot-polymarket-ws",
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


class PolymarketWsConnector:
    def __init__(
        self,
        *,
        producer: KafkaJsonProducer,
        market_asset_ids: list[str],
        user_markets: list[str] | None = None,
    ) -> None:
        self.producer = producer
        self.market_asset_ids = market_asset_ids
        self.user_markets = user_markets or []

        self.market_url = os.getenv(
            "POLYMARKET_WS_MARKET_URL",
            "wss://ws-subscriptions-clob.polymarket.com/ws/market",
        )

        self.user_url = os.getenv(
            "POLYMARKET_WS_USER_URL",
            "wss://ws-subscriptions-clob.polymarket.com/ws/user",
        )

        self.market_enabled = os.getenv("POLYMARKET_WS_MARKET_ENABLED", "true").lower() == "true"
        self.user_enabled = os.getenv("POLYMARKET_WS_USER_ENABLED", "false").lower() == "true"

        self.orderbook_topic = os.getenv("POLYMARKET_WS_ORDERBOOK_TOPIC", "poly-orderbook")
        self.user_orders_topic = os.getenv("POLYMARKET_WS_USER_ORDERS_TOPIC", "orders")
        self.user_fills_topic = os.getenv("POLYMARKET_WS_USER_FILLS_TOPIC", "fills")

        self.ping_interval_seconds = float(os.getenv("POLYMARKET_WS_PING_INTERVAL_SECONDS", "10"))
        self.reconnect_initial_seconds = float(os.getenv("POLYMARKET_WS_RECONNECT_INITIAL_SECONDS", "2"))
        self.reconnect_max_seconds = float(os.getenv("POLYMARKET_WS_RECONNECT_MAX_SECONDS", "60"))

        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        tasks: list[asyncio.Task[None]] = []

        if self.market_enabled:
            if not self.market_asset_ids:
                logger.warning("Market WebSocket enabled, but no market asset IDs were provided.")
            else:
                tasks.append(asyncio.create_task(self.run_market_channel()))

        if self.user_enabled:
            tasks.append(asyncio.create_task(self.run_user_channel()))
        else:
            logger.info("User WebSocket disabled. Set POLYMARKET_WS_USER_ENABLED=true to enable it.")

        if not tasks:
            logger.warning("No WebSocket channels enabled.")
            return

        await asyncio.gather(*tasks)

    async def run_market_channel(self) -> None:
        reconnect_delay = self.reconnect_initial_seconds

        while not self._stop_event.is_set():
            try:
                await self._connect_market_channel()
                reconnect_delay = self.reconnect_initial_seconds
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Market WebSocket error: %s", exc)

            if self._stop_event.is_set():
                break

            logger.info("Reconnecting market channel in %.1f seconds", reconnect_delay)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, self.reconnect_max_seconds)

    async def _connect_market_channel(self) -> None:
        logger.info("Connecting market WebSocket: %s", self.market_url)

        async with websockets.connect(self.market_url, ping_interval=None) as websocket:
            subscription = {
                "assets_ids": self.market_asset_ids,
                "type": "market",
                "custom_feature_enabled": True,
            }

            await websocket.send(json.dumps(subscription))
            logger.info("Subscribed to market assets: %s", self.market_asset_ids)

            heartbeat_task = asyncio.create_task(self._heartbeat(websocket))

            try:
                async for raw_message in websocket:
                    if self._stop_event.is_set():
                        break

                    await self._handle_market_raw_message(raw_message)
            finally:
                heartbeat_task.cancel()

                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _handle_market_raw_message(self, raw_message: Any) -> None:
        if raw_message == "PONG":
            logger.debug("Received PONG from market channel")
            return

        if not isinstance(raw_message, str):
            logger.debug("Ignoring non-string market message: %r", raw_message)
            return

        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.warning("Could not decode market WS message: %s", raw_message[:500])
            return

        messages = payload if isinstance(payload, list) else [payload]

        for message in messages:
            if not isinstance(message, dict):
                continue

            normalized_events = normalize_market_ws_message(message)

            for normalized_event in normalized_events:
                kafka_event = normalized_market_event_to_kafka(
                    normalized_event,
                    topic=self.orderbook_topic,
                )

                self.producer.publish(kafka_event)

                logger.info(
                    "Published market WS event event_type=%s market=%s asset_id=%s topic=%s",
                    normalized_event.event_type,
                    normalized_event.market,
                    normalized_event.asset_id,
                    self.orderbook_topic,
                )

    async def run_user_channel(self) -> None:
        reconnect_delay = self.reconnect_initial_seconds

        while not self._stop_event.is_set():
            try:
                await self._connect_user_channel()
                reconnect_delay = self.reconnect_initial_seconds
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("User WebSocket error: %s", exc)

            if self._stop_event.is_set():
                break

            logger.info("Reconnecting user channel in %.1f seconds", reconnect_delay)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, self.reconnect_max_seconds)

    async def _connect_user_channel(self) -> None:
        api_key = os.getenv("POLYMARKET_API_KEY", "")
        api_secret = os.getenv("POLYMARKET_API_SECRET", "")
        api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE", "")

        if not api_key or not api_secret or not api_passphrase:
            raise ValueError(
                "User WebSocket enabled, but POLYMARKET_API_KEY, "
                "POLYMARKET_API_SECRET or POLYMARKET_API_PASSPHRASE is missing."
            )

        logger.info("Connecting user WebSocket: %s", self.user_url)

        async with websockets.connect(self.user_url, ping_interval=None) as websocket:
            subscription: dict[str, Any] = {
                "auth": {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "passphrase": api_passphrase,
                },
                "type": "user",
            }

            if self.user_markets:
                subscription["markets"] = self.user_markets

            await websocket.send(json.dumps(subscription))
            logger.info("Subscribed to user channel markets=%s", self.user_markets or "all")

            heartbeat_task = asyncio.create_task(self._heartbeat(websocket))

            try:
                async for raw_message in websocket:
                    if self._stop_event.is_set():
                        break

                    await self._handle_user_raw_message(raw_message)
            finally:
                heartbeat_task.cancel()

                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _handle_user_raw_message(self, raw_message: Any) -> None:
        if raw_message == "PONG":
            logger.debug("Received PONG from user channel")
            return

        if not isinstance(raw_message, str):
            return

        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.warning("Could not decode user WS message: %s", raw_message[:500])
            return

        messages = payload if isinstance(payload, list) else [payload]

        for message in messages:
            if not isinstance(message, dict):
                continue

            event_type = str(message.get("event_type") or message.get("type") or "unknown").lower()

            if event_type in {"trade", "matched", "fill"}:
                topic = self.user_fills_topic
            elif event_type in {"order", "placement", "update", "cancellation"}:
                topic = self.user_orders_topic
            else:
                topic = self.user_orders_topic

            key = ":".join(
                [
                    str(message.get("market") or "unknown_market"),
                    str(message.get("asset_id") or "unknown_asset"),
                    event_type,
                ]
            )

            event = KafkaEvent(
                topic=topic,
                key=key,
                value={
                    "source": "polymarket_ws",
                    "channel": "user",
                    "event_type": event_type,
                    "received_at": utc_now_iso(),
                    "raw": message,
                },
            )

            self.producer.publish(event)
            logger.info("Published user WS event event_type=%s topic=%s", event_type, topic)

    async def _heartbeat(self, websocket: Any) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(self.ping_interval_seconds)

            try:
                await websocket.send("PING")
                logger.debug("Sent PING")
            except Exception:
                logger.exception("Failed to send PING")
                raise


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Polymarket WebSocket connector")

    parser.add_argument(
        "--asset-ids",
        default=os.getenv("POLYMARKET_WS_MARKET_ASSET_IDS", ""),
        help="Comma-separated CLOB asset/token IDs for market channel",
    )

    parser.add_argument(
        "--user-markets",
        default=os.getenv("POLYMARKET_WS_USER_MARKETS", ""),
        help="Comma-separated condition IDs for user channel",
    )

    parser.add_argument(
        "--run-seconds",
        type=float,
        default=float(os.getenv("POLYMARKET_WS_RUN_SECONDS", "30")),
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

    asset_ids = parse_csv_env(args.asset_ids)
    user_markets = parse_csv_env(args.user_markets)

    producer = KafkaJsonProducer()

    connector = PolymarketWsConnector(
        producer=producer,
        market_asset_ids=asset_ids,
        user_markets=user_markets,
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