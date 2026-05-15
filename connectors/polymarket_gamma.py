"""
Polymarket Gamma connector.

Este módulo descobre mercados ativos de Bitcoin na Polymarket.

Responsabilidades:
- Chamar GET /markets na Gamma API.
- Filtrar mercados ativos relacionados a Bitcoin.
- Detectar timeframe pela pergunta do mercado.
- Extrair market_id, condition_id, question, end_time e tokens YES/NO.

Este módulo NÃO executa ordens.
Este módulo NÃO usa chave privada.
Este módulo NÃO faz trading real.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()


SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "1d"}


@dataclass(frozen=True)
class PolymarketMarket:
    market_id: str
    condition_id: str | None
    question: str
    end_time: str | None
    timeframe: str
    yes_token_id: str | None
    no_token_id: str | None


def parse_json_list(value: Any) -> list[Any]:
    """
    Alguns campos da Gamma API podem vir como lista real ou como string JSON.

    Exemplos:
    - ["Yes", "No"]
    - "[\"Yes\", \"No\"]"

    Esta função transforma ambos em lista Python.
    """
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]

        if isinstance(parsed, list):
            return parsed

        return [parsed]

    return [value]


def detect_timeframe(question: str) -> str | None:
    """
    Detecta o timeframe a partir da pergunta do mercado.

    Retorna:
    - 5m
    - 15m
    - 1h
    - 1d
    - None
    """
    text = question.lower()

    if re.search(r"\b(5m|5 min|5 mins|5 minute|5 minutes|5-minute)\b", text):
        return "5m"

    if re.search(r"\b(15m|15 min|15 mins|15 minute|15 minutes|15-minute)\b", text):
        return "15m"

    if re.search(r"\b(1h|1 hr|1 hour|hourly|1-hour)\b", text):
        return "1h"

    if re.search(r"\b(1d|1 day|daily|1-day|today|tomorrow)\b", text):
        return "1d"

    duration = detect_duration_from_time_range(question)

    if duration == 5:
        return "5m"

    if duration == 15:
        return "15m"

    if duration == 60:
        return "1h"

    if duration in {1439, 1440, 1441}:
        return "1d"

    return None


def detect_duration_from_time_range(question: str) -> int | None:
    """
    Detecta duração quando a pergunta tem intervalo de horário.

    Exemplo:
    Bitcoin Up or Down - May 14, 3:00PM-3:15PM ET

    Nesse caso retorna 15.
    """
    text = question.upper()

    pattern = re.compile(
        r"(?P<h1>\d{1,2}):(?P<m1>\d{2})\s*(?P<ampm1>AM|PM)?"
        r"\s*[-–]\s*"
        r"(?P<h2>\d{1,2}):(?P<m2>\d{2})\s*(?P<ampm2>AM|PM)?"
    )

    match = pattern.search(text)

    if not match:
        return None

    h1 = int(match.group("h1"))
    m1 = int(match.group("m1"))
    h2 = int(match.group("h2"))
    m2 = int(match.group("m2"))

    ampm1 = match.group("ampm1")
    ampm2 = match.group("ampm2")

    if ampm1 is None and ampm2 is not None:
        ampm1 = ampm2

    start = convert_to_minutes(h1, m1, ampm1)
    end = convert_to_minutes(h2, m2, ampm2)

    if end < start:
        end += 24 * 60

    return end - start


def convert_to_minutes(hour: int, minute: int, ampm: str | None) -> int:
    if ampm == "AM":
        hour = 0 if hour == 12 else hour

    if ampm == "PM":
        hour = 12 if hour == 12 else hour + 12

    return hour * 60 + minute


def looks_like_bitcoin_market(raw_market: dict[str, Any]) -> bool:
    """
    Verifica se o mercado parece ser de Bitcoin.

    Usamos isso como proteção adicional, porque filtros por tag podem variar.
    """
    parts = [
        raw_market.get("question"),
        raw_market.get("slug"),
        raw_market.get("description"),
        raw_market.get("category"),
    ]

    text = " ".join(str(part or "") for part in parts).lower()

    return bool(re.search(r"\b(bitcoin|btc|btcusd|btcusdt)\b", text))


def normalize_market(raw_market: dict[str, Any]) -> PolymarketMarket | None:
    """
    Transforma um mercado bruto da Gamma API em um objeto limpo do nosso projeto.
    """
    market_id = str(raw_market.get("id") or "").strip()
    question = str(raw_market.get("question") or "").strip()

    if not market_id or not question:
        return None

    timeframe = detect_timeframe(question)

    if timeframe is None:
        return None

    outcomes = parse_json_list(raw_market.get("outcomes"))
    token_ids = parse_json_list(raw_market.get("clobTokenIds"))

    yes_token_id = None
    no_token_id = None

    for index, outcome in enumerate(outcomes):
        outcome_name = str(outcome).lower().strip()
        token_id = str(token_ids[index]) if index < len(token_ids) else None

        if outcome_name == "yes":
            yes_token_id = token_id

        if outcome_name == "no":
            no_token_id = token_id

    if yes_token_id is None and len(token_ids) >= 1:
        yes_token_id = str(token_ids[0])

    if no_token_id is None and len(token_ids) >= 2:
        no_token_id = str(token_ids[1])

    return PolymarketMarket(
        market_id=market_id,
        condition_id=raw_market.get("conditionId") or raw_market.get("condition_id"),
        question=question,
        end_time=raw_market.get("endDateIso")
        or raw_market.get("endDate")
        or raw_market.get("end_time"),
        timeframe=timeframe,
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
    )


class PolymarketGammaClient:
    """
    Cliente simples da Gamma API.
    """

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "POLYMARKET_GAMMA_BASE_URL",
            "https://gamma-api.polymarket.com",
        ).rstrip("/")

        self.timeout_seconds = float(
            os.getenv("POLYMARKET_GAMMA_REQUEST_TIMEOUT_SECONDS", "15")
        )

        self.bitcoin_tag = os.getenv("POLYMARKET_GAMMA_BITCOIN_TAG", "bitcoin")
        self.bitcoin_tag_id = os.getenv("POLYMARKET_GAMMA_BITCOIN_TAG_ID", "")

        self.limit = int(os.getenv("POLYMARKET_GAMMA_MARKETS_LIMIT", "100"))
        self.max_pages = int(os.getenv("POLYMARKET_GAMMA_MARKETS_MAX_PAGES", "5"))

        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self.client.close()

    def fetch_markets_page(self, offset: int = 0) -> list[dict[str, Any]]:
        """
        Busca uma página de mercados.

        Usamos:
        - active=true
        - closed=false
        - tag=bitcoin quando não houver tag_id
        """
        params: dict[str, Any] = {
            "limit": self.limit,
            "offset": offset,
            "active": "true",
            "closed": "false",
        }

        if self.bitcoin_tag_id:
            params["tag_id"] = self.bitcoin_tag_id
        else:
            params["tag"] = self.bitcoin_tag

        response = self.client.get("/markets", params=params)
        response.raise_for_status()

        payload = response.json()

        if isinstance(payload, list):
            return payload

        if isinstance(payload, dict):
            for key in ("markets", "data", "results"):
                if isinstance(payload.get(key), list):
                    return payload[key]

        raise ValueError("Formato inesperado na resposta da Gamma API")

    def discover_bitcoin_markets(self) -> list[PolymarketMarket]:
        """
        Busca e normaliza mercados ativos de Bitcoin.
        """
        discovered: list[PolymarketMarket] = []

        for page in range(self.max_pages):
            offset = page * self.limit
            raw_markets = self.fetch_markets_page(offset=offset)

            if not raw_markets:
                break

            for raw_market in raw_markets:
                if not looks_like_bitcoin_market(raw_market):
                    continue

                market = normalize_market(raw_market)

                if market is None:
                    continue

                discovered.append(market)

            if len(raw_markets) < self.limit:
                break

        return discovered


def market_to_dict(market: PolymarketMarket) -> dict[str, Any]:
    return asdict(market)


def main() -> None:
    client = PolymarketGammaClient()

    try:
        markets = client.discover_bitcoin_markets()
    finally:
        client.close()

    print(json.dumps([market_to_dict(market) for market in markets], indent=2))
    print(f"\nTotal markets discovered: {len(markets)}")


if __name__ == "__main__":
    main()