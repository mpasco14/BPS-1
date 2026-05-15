"""
Free on-chain connector.

Responsabilidades:
- Coletar dados gratuitos de rede Bitcoin via Mempool.space.
- Coletar dados gratuitos de stablecoins via DefiLlama.
- Normalizar eventos on-chain.
- Publicar eventos no Redpanda/Kafka no tópico onchain-events.

Este módulo NÃO usa API key.
Este módulo NÃO acessa carteiras.
Este módulo NÃO move fundos.
Este módulo NÃO substitui integralmente provedores pagos como Glassnode.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from confluent_kafka import Producer
from dotenv import load_dotenv


load_dotenv()


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FreeOnchainEvent:
    source: str
    provider: str
    event_type: str
    asset: str
    category: str
    interval: str
    timestamp: int
    collected_at: str
    value: Any
    raw: dict[str, Any]
    score: float | None = None


@dataclass(frozen=True)
class KafkaEvent:
    topic: str
    key: str
    value: dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def unix_now() -> int:
    return int(time.time())


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []

    return [item.strip().upper() for item in value.split(",") if item.strip()]


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, round(value, 6)))


def calculate_fee_pressure_score(recommended_fees: dict[str, Any]) -> float | None:
    """
    Score simples de pressão de fees.

    Regra inicial:
    - fastestFee <= 5 sat/vB: baixo
    - fastestFee >= 100 sat/vB: alto
    """
    fastest_fee = safe_float(recommended_fees.get("fastestFee"))

    if fastest_fee is None:
        return None

    return clamp_score(fastest_fee / 100.0)


def calculate_mempool_congestion_score(mempool_stats: dict[str, Any]) -> float | None:
    """
    Score simples de congestão do mempool.

    Usamos vsize como proxy inicial.
    """
    vsize = safe_float(mempool_stats.get("vsize"))

    if vsize is None:
        return None

    return clamp_score(vsize / 300_000_000)


def extract_stablecoin_supply_usd(value: dict[str, Any]) -> float | None:
    """
    Extrai supply aproximado em USD de um item de stablecoin da DefiLlama.

    Formatos possíveis:
    - {"circulating": {"peggedUSD": 1000000}}
    - {"circulating": 1000000}
    - {"mcap": 1000000}
    """
    circulating = value.get("circulating")

    if isinstance(circulating, dict):
        supply = safe_float(circulating.get("peggedUSD"))

        if supply is not None:
            return supply

    if circulating is not None:
        supply = safe_float(circulating)

        if supply is not None:
            return supply

    return safe_float(value.get("mcap"))


def calculate_stablecoin_liquidity_score(value: dict[str, Any]) -> float | None:
    """
    Score simples de liquidez de stablecoin.

    Normalização inicial:
    - 0 USD       -> 0
    - 100B USD+   -> 1
    """
    supply = extract_stablecoin_supply_usd(value)

    if supply is None:
        return None

    return clamp_score(supply / 100_000_000_000)


def normalize_mempool_event(
    *,
    event_type: str,
    value: Any,
    score: float | None = None,
) -> FreeOnchainEvent:
    raw = value if isinstance(value, dict) else {"value": value}

    return FreeOnchainEvent(
        source="free_onchain",
        provider="mempool_space",
        event_type=event_type,
        asset="BTC",
        category="bitcoin_network",
        interval=os.getenv("FREE_ONCHAIN_INTERVAL", "snapshot"),
        timestamp=unix_now(),
        collected_at=utc_now_iso(),
        value=value,
        raw=raw,
        score=score,
    )


def normalize_stablecoin_event(
    *,
    stablecoin_symbol: str,
    value: dict[str, Any],
) -> FreeOnchainEvent:
    supply_usd = extract_stablecoin_supply_usd(value)
    score = calculate_stablecoin_liquidity_score(value)

    return FreeOnchainEvent(
        source="free_onchain",
        provider="defillama",
        event_type="stablecoin_supply",
        asset=stablecoin_symbol.upper(),
        category="stablecoin_liquidity",
        interval=os.getenv("FREE_ONCHAIN_INTERVAL", "snapshot"),
        timestamp=unix_now(),
        collected_at=utc_now_iso(),
        value={
            "symbol": stablecoin_symbol.upper(),
            "supply_usd": supply_usd,
        },
        raw=value,
        score=score,
    )


def event_to_kafka(event: FreeOnchainEvent, topic: str) -> KafkaEvent:
    key = f"{event.asset}:{event.event_type}:{event.interval}:{event.timestamp}"

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
                "client.id": "btc-polymarket-bot-free-onchain",
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


class FreeOnchainClient:
    def __init__(
        self,
        *,
        mempool_base_url: str | None = None,
        defillama_base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.mempool_base_url = (
            mempool_base_url
            or os.getenv("MEMPOOL_BASE_URL")
            or "https://mempool.space/api"
        ).rstrip("/")

        self.defillama_base_url = (
            defillama_base_url
            or os.getenv("DEFILLAMA_STABLECOINS_BASE_URL")
            or os.getenv("DEFILLAMA_BASE_URL")
            or "https://stablecoins.llama.fi"
        ).rstrip("/")

        # Se o usuário deixou DEFILLAMA_BASE_URL=https://api.llama.fi,
        # usamos o host correto para stablecoins.
        if self.defillama_base_url == "https://api.llama.fi":
            self.defillama_base_url = "https://stablecoins.llama.fi"

        self.timeout_seconds = float(
            timeout_seconds
            or os.getenv("FREE_ONCHAIN_TIMEOUT_SECONDS")
            or 20
        )

        self.mempool_client = httpx.Client(
            base_url=self.mempool_base_url,
            timeout=self.timeout_seconds,
            headers={
                "Accept": "application/json",
                "User-Agent": "btc-polymarket-bot/0.1",
            },
        )

        self.defillama_client = httpx.Client(
            base_url=self.defillama_base_url,
            timeout=self.timeout_seconds,
            headers={
                "Accept": "application/json",
                "User-Agent": "btc-polymarket-bot/0.1",
            },
        )

    def close(self) -> None:
        self.mempool_client.close()
        self.defillama_client.close()

    def __enter__(self) -> "FreeOnchainClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def fetch_recommended_fees(self) -> dict[str, Any]:
        response = self.mempool_client.get("/v1/fees/recommended")
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Resposta inesperada de /v1/fees/recommended")

        return payload

    def fetch_mempool_stats(self) -> dict[str, Any]:
        response = self.mempool_client.get("/mempool")
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Resposta inesperada de /mempool")

        return payload

    def fetch_block_tip_height(self) -> int | None:
        response = self.mempool_client.get("/blocks/tip/height")
        response.raise_for_status()

        text = response.text.strip()

        try:
            return int(text)
        except ValueError:
            return None

    def fetch_stablecoins_payload(self) -> dict[str, Any]:
        response = self.defillama_client.get("/stablecoins")
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Resposta inesperada de /stablecoins")

        return payload

    def collect_mempool_events(self) -> list[FreeOnchainEvent]:
        events: list[FreeOnchainEvent] = []

        try:
            fees = self.fetch_recommended_fees()
            events.append(
                normalize_mempool_event(
                    event_type="mempool_fees",
                    value=fees,
                    score=calculate_fee_pressure_score(fees),
                )
            )
        except Exception as exc:
            logger.exception("Failed to collect mempool fees: %s", exc)

        try:
            mempool_stats = self.fetch_mempool_stats()
            events.append(
                normalize_mempool_event(
                    event_type="mempool_stats",
                    value=mempool_stats,
                    score=calculate_mempool_congestion_score(mempool_stats),
                )
            )
        except Exception as exc:
            logger.exception("Failed to collect mempool stats: %s", exc)

        try:
            height = self.fetch_block_tip_height()

            if height is not None:
                events.append(
                    normalize_mempool_event(
                        event_type="block_tip_height",
                        value={"height": height},
                        score=None,
                    )
                )
        except Exception as exc:
            logger.exception("Failed to collect block tip height: %s", exc)

        return events

    def collect_stablecoin_events(self) -> list[FreeOnchainEvent]:
        wanted_symbols = parse_csv_env(
            os.getenv("FREE_ONCHAIN_STABLECOINS", "USDT,USDC,DAI")
        )

        events: list[FreeOnchainEvent] = []

        try:
            payload = self.fetch_stablecoins_payload()
        except Exception as exc:
            logger.exception("Failed to collect stablecoin data: %s", exc)
            return events

        assets = payload.get("peggedAssets", [])

        if not isinstance(assets, list):
            logger.warning("DefiLlama stablecoins payload has no peggedAssets list")
            return events

        for item in assets:
            if not isinstance(item, dict):
                continue

            symbol = str(item.get("symbol") or "").upper()

            if symbol not in wanted_symbols:
                continue

            events.append(
                normalize_stablecoin_event(
                    stablecoin_symbol=symbol,
                    value=item,
                )
            )

        return events

    def collect_events(self) -> list[FreeOnchainEvent]:
        events: list[FreeOnchainEvent] = []
        events.extend(self.collect_mempool_events())
        events.extend(self.collect_stablecoin_events())
        return events


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch free on-chain metrics")

    parser.add_argument(
        "--publish",
        action="store_true",
        default=parse_bool(os.getenv("FREE_ONCHAIN_PUBLISH_TO_KAFKA"), default=True),
        help="Publish events to Kafka/Redpanda",
    )

    parser.add_argument(
        "--run-seconds",
        type=float,
        default=float(os.getenv("FREE_ONCHAIN_RUN_SECONDS", "0")),
        help="How long to run. 0 means collect once.",
    )

    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=60.0,
        help="Sleep interval when run-seconds is greater than 0.",
    )

    return parser


def publish_events(events: list[FreeOnchainEvent], topic: str) -> None:
    producer = KafkaJsonProducer()

    for event in events:
        producer.publish(event_to_kafka(event, topic=topic))

    producer.flush()

    logger.info("Published %s free on-chain events to topic=%s", len(events), topic)


def collect_once(*, publish: bool) -> list[FreeOnchainEvent]:
    topic = os.getenv("FREE_ONCHAIN_TOPIC", "onchain-events")

    with FreeOnchainClient() as client:
        events = client.collect_events()

    print(json.dumps([asdict(event) for event in events], indent=2, ensure_ascii=False))
    print(f"\nTotal free on-chain events: {len(events)}")

    if publish and events:
        publish_events(events, topic=topic)

    return events


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    if args.run_seconds <= 0:
        collect_once(publish=args.publish)
        return

    started_at = time.monotonic()

    while time.monotonic() - started_at < args.run_seconds:
        collect_once(publish=args.publish)
        time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    main()