"""
Sentiment connector.

Responsabilidades:
- Coletar notícias cripto de fontes gratuitas via RSS.
- Opcionalmente coletar CryptoCompare News API se houver API key.
- Extrair keywords relevantes:
  ETF, SEC, CPI, Fed, hack, liquidation, lawsuit, approval, ban.
- Calcular sentiment_score inicial baseado em regras.
- Publicar eventos no Redpanda/Kafka no tópico sentiment-events.

Este módulo NÃO faz recomendação de investimento.
Este módulo NÃO executa ordens.
Este módulo NÃO substitui análise humana ou modelo NLP avançado.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from confluent_kafka import Producer
from dotenv import load_dotenv


load_dotenv()


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsItem:
    provider: str
    title: str
    summary: str | None
    url: str | None
    published_at: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class SentimentEvent:
    source: str
    provider: str
    event_type: str
    asset: str
    category: str
    interval: str
    timestamp: int
    collected_at: str

    sentiment_score: float
    volume_mentions: int
    keywords: list[str]
    positive_hits: list[str]
    negative_hits: list[str]
    neutral_hits: list[str]

    articles: list[dict[str, Any]]
    raw: dict[str, Any]


@dataclass(frozen=True)
class KafkaEvent:
    topic: str
    key: str
    value: dict[str, Any]


DEFAULT_TRACKED_KEYWORDS = [
    "ETF",
    "SEC",
    "CPI",
    "Fed",
    "hack",
    "liquidation",
    "lawsuit",
    "approval",
    "ban",
]


POSITIVE_KEYWORDS = {
    "approval": 0.35,
    "approved": 0.35,
    "approve": 0.25,
    "etf approval": 0.45,
    "inflow": 0.18,
    "inflows": 0.18,
    "rally": 0.22,
    "surge": 0.18,
    "record high": 0.22,
    "adoption": 0.16,
    "bullish": 0.20,
    "rate cut": 0.14,
}

NEGATIVE_KEYWORDS = {
    "hack": -0.35,
    "hacked": -0.35,
    "exploit": -0.30,
    "liquidation": -0.28,
    "liquidations": -0.28,
    "lawsuit": -0.25,
    "ban": -0.30,
    "banned": -0.30,
    "sec sues": -0.28,
    "crash": -0.30,
    "plunge": -0.24,
    "selloff": -0.24,
    "bearish": -0.20,
    "outflow": -0.16,
    "outflows": -0.16,
}

NEUTRAL_KEYWORDS = {
    "ETF",
    "SEC",
    "CPI",
    "Fed",
    "Federal Reserve",
    "inflation",
    "rate decision",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def unix_now() -> int:
    return int(time.time())


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_csv_env(value: str | None, *, upper: bool = False) -> list[str]:
    if not value:
        return []

    items = [item.strip() for item in value.split(",") if item.strip()]

    if upper:
        return [item.upper() for item in items]

    return items


def clamp_sentiment_score(value: float) -> float:
    return max(-1.0, min(1.0, round(value, 6)))


def strip_html(text: str | None) -> str:
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def parse_rss_datetime(value: str | None) -> str | None:
    if not value:
        return None

    try:
        parsed = parsedate_to_datetime(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return value


def provider_from_feed_url(feed_url: str) -> str:
    host = urlparse(feed_url).netloc.lower()

    if "cointelegraph" in host:
        return "cointelegraph"

    if "decrypt" in host:
        return "decrypt"

    if "coindesk" in host:
        return "coindesk"

    return host or "rss"


def article_text(item: NewsItem) -> str:
    return f"{item.title or ''} {item.summary or ''}".strip()


def contains_btc_context(text: str) -> bool:
    """
    Mantém notícias com contexto BTC/cripto.

    Como alguns feeds são cripto amplos, aceitamos termos de mercado cripto
    e não apenas Bitcoin.
    """
    lowered = text.lower()

    patterns = [
        r"\bbitcoin\b",
        r"\bbtc\b",
        r"\bcrypto\b",
        r"\bcryptocurrency\b",
        r"\bblockchain\b",
        r"\betf\b",
        r"\bstablecoin\b",
        r"\bethereum\b",
        r"\beth\b",
    ]

    return any(re.search(pattern, lowered) for pattern in patterns)


def find_keywords(text: str, keywords: list[str]) -> list[str]:
    found: list[str] = []
    lowered = text.lower()

    for keyword in keywords:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"

        if re.search(pattern, lowered):
            found.append(keyword)

    return sorted(set(found), key=lambda item: item.lower())


def find_weighted_hits(text: str, weights: dict[str, float]) -> list[str]:
    hits: list[str] = []
    lowered = text.lower()

    for keyword in weights:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"

        if re.search(pattern, lowered):
            hits.append(keyword)

    return sorted(set(hits))


def calculate_article_sentiment_score(text: str) -> tuple[float, list[str], list[str], list[str]]:
    positive_hits = find_weighted_hits(text, POSITIVE_KEYWORDS)
    negative_hits = find_weighted_hits(text, NEGATIVE_KEYWORDS)
    neutral_hits = find_keywords(text, list(NEUTRAL_KEYWORDS))

    score = 0.0

    lowered = text.lower()

    for keyword, weight in POSITIVE_KEYWORDS.items():
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"

        if re.search(pattern, lowered):
            score += weight

    for keyword, weight in NEGATIVE_KEYWORDS.items():
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"

        if re.search(pattern, lowered):
            score += weight

    return clamp_sentiment_score(score), positive_hits, negative_hits, neutral_hits


def calculate_batch_sentiment(
    items: list[NewsItem],
    tracked_keywords: list[str],
) -> SentimentEvent:
    relevant_items = [
        item
        for item in items
        if contains_btc_context(article_text(item))
    ]

    article_outputs: list[dict[str, Any]] = []

    all_keywords: list[str] = []
    all_positive_hits: list[str] = []
    all_negative_hits: list[str] = []
    all_neutral_hits: list[str] = []

    total_score = 0.0

    for item in relevant_items:
        text = article_text(item)
        keywords = find_keywords(text, tracked_keywords)
        score, positive_hits, negative_hits, neutral_hits = calculate_article_sentiment_score(text)

        total_score += score
        all_keywords.extend(keywords)
        all_positive_hits.extend(positive_hits)
        all_negative_hits.extend(negative_hits)
        all_neutral_hits.extend(neutral_hits)

        article_outputs.append(
            {
                "provider": item.provider,
                "title": item.title,
                "summary": item.summary,
                "url": item.url,
                "published_at": item.published_at,
                "keywords": keywords,
                "sentiment_score": score,
                "positive_hits": positive_hits,
                "negative_hits": negative_hits,
                "neutral_hits": neutral_hits,
            }
        )

    volume_mentions = len(relevant_items)

    if volume_mentions == 0:
        final_score = 0.0
    else:
        final_score = clamp_sentiment_score(total_score / volume_mentions)

    providers = sorted({item.provider for item in relevant_items}) or ["none"]

    return SentimentEvent(
        source="sentiment",
        provider="+".join(providers),
        event_type="sentiment_snapshot",
        asset="BTC",
        category="social_news_sentiment",
        interval=os.getenv("SENTIMENT_INTERVAL", "snapshot"),
        timestamp=unix_now(),
        collected_at=utc_now_iso(),
        sentiment_score=final_score,
        volume_mentions=volume_mentions,
        keywords=sorted(set(all_keywords), key=lambda item: item.lower()),
        positive_hits=sorted(set(all_positive_hits)),
        negative_hits=sorted(set(all_negative_hits)),
        neutral_hits=sorted(set(all_neutral_hits), key=lambda item: item.lower()),
        articles=article_outputs,
        raw={
            "total_items": len(items),
            "relevant_items": volume_mentions,
        },
    )


def event_to_kafka(event: SentimentEvent, topic: str) -> KafkaEvent:
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
                "client.id": "btc-polymarket-bot-sentiment",
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


class SentimentClient:
    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self.timeout_seconds = float(
            timeout_seconds
            or os.getenv("SENTIMENT_TIMEOUT_SECONDS")
            or 20
        )

        self.client = httpx.Client(
            timeout=self.timeout_seconds,
            headers={
                "Accept": "application/rss+xml, application/xml, text/xml, application/json",
                "User-Agent": "btc-polymarket-bot/0.1",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "SentimentClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def fetch_rss_feed(self, feed_url: str) -> list[NewsItem]:
        response = self.client.get(feed_url)
        response.raise_for_status()

        provider = provider_from_feed_url(feed_url)

        root = ET.fromstring(response.text.encode("utf-8"))

        items: list[NewsItem] = []

        for item in root.findall(".//item"):
            title = item.findtext("title") or ""
            link = item.findtext("link")
            description = item.findtext("description")
            pub_date = item.findtext("pubDate")

            title = strip_html(title)
            summary = strip_html(description)
            published_at = parse_rss_datetime(pub_date)

            if not title:
                continue

            items.append(
                NewsItem(
                    provider=provider,
                    title=title,
                    summary=summary,
                    url=link,
                    published_at=published_at,
                    raw={
                        "title": title,
                        "link": link,
                        "description": summary,
                        "pubDate": pub_date,
                    },
                )
            )

        return items

    def fetch_rss_items(self, feed_urls: list[str]) -> list[NewsItem]:
        items: list[NewsItem] = []

        for feed_url in feed_urls:
            try:
                items.extend(self.fetch_rss_feed(feed_url))
            except Exception as exc:
                logger.exception("Failed to fetch RSS feed=%s: %s", feed_url, exc)

        return items

    def fetch_cryptocompare_items(self) -> list[NewsItem]:
        api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")

        if not api_key:
            return []

        base_url = os.getenv("CRYPTOCOMPARE_NEWS_BASE_URL", "https://min-api.cryptocompare.com").rstrip("/")
        path = os.getenv("CRYPTOCOMPARE_NEWS_PATH", "/data/v2/news/")

        response = self.client.get(
            f"{base_url}{path}",
            params={
                "lang": "EN",
                "api_key": api_key,
            },
        )
        response.raise_for_status()

        payload = response.json()

        data = payload.get("Data", [])

        if not isinstance(data, list):
            return []

        items: list[NewsItem] = []

        for entry in data:
            if not isinstance(entry, dict):
                continue

            title = strip_html(str(entry.get("title") or ""))
            summary = strip_html(str(entry.get("body") or ""))
            url = entry.get("url")
            published_on = entry.get("published_on")

            published_at = None

            if published_on is not None:
                try:
                    published_at = datetime.fromtimestamp(
                        int(published_on),
                        tz=timezone.utc,
                    ).isoformat()
                except Exception:
                    published_at = None

            if not title:
                continue

            items.append(
                NewsItem(
                    provider="cryptocompare",
                    title=title,
                    summary=summary,
                    url=url,
                    published_at=published_at,
                    raw=entry,
                )
            )

        return items

    def collect_items(self) -> list[NewsItem]:
        provider = os.getenv("SENTIMENT_PROVIDER", "rss").lower()

        rss_feeds = parse_csv_env(
            os.getenv(
                "SENTIMENT_RSS_FEEDS",
                "https://cointelegraph.com/rss,https://decrypt.co/feed",
            )
        )

        items: list[NewsItem] = []

        if provider in {"rss", "mixed"}:
            items.extend(self.fetch_rss_items(rss_feeds))

        if provider in {"cryptocompare", "mixed"}:
            items.extend(self.fetch_cryptocompare_items())

        return deduplicate_news_items(items)


def deduplicate_news_items(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    unique: list[NewsItem] = []

    for item in items:
        key = item.url or f"{item.provider}:{item.title}"

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    return unique


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch crypto sentiment data")

    parser.add_argument(
        "--publish",
        action="store_true",
        default=parse_bool(os.getenv("SENTIMENT_PUBLISH_TO_KAFKA"), default=True),
        help="Publish sentiment event to Kafka/Redpanda",
    )

    parser.add_argument(
        "--run-seconds",
        type=float,
        default=float(os.getenv("SENTIMENT_RUN_SECONDS", "0")),
        help="How long to run. 0 means collect once.",
    )

    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=300.0,
        help="Sleep interval when run-seconds is greater than 0.",
    )

    return parser


def collect_once(*, publish: bool) -> SentimentEvent:
    max_items = int(os.getenv("SENTIMENT_MAX_ITEMS", "50"))
    topic = os.getenv("SENTIMENT_TOPIC", "sentiment-events")
    tracked_keywords = parse_csv_env(
        os.getenv("SENTIMENT_KEYWORDS", ",".join(DEFAULT_TRACKED_KEYWORDS))
    )

    with SentimentClient() as client:
        items = client.collect_items()

    items = items[:max_items]

    event = calculate_batch_sentiment(
        items=items,
        tracked_keywords=tracked_keywords,
    )

    print(json.dumps(asdict(event), indent=2, ensure_ascii=False))
    print(f"\nTotal sentiment articles processed: {len(items)}")
    print(f"Relevant BTC/crypto mentions: {event.volume_mentions}")
    print(f"Sentiment score: {event.sentiment_score}")

    if publish:
        producer = KafkaJsonProducer()
        producer.publish(event_to_kafka(event, topic=topic))
        producer.flush()

        logger.info("Published sentiment event to topic=%s", topic)

    return event


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