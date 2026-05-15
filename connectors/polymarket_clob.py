"""
Polymarket CLOB connector.

Este módulo lê dados públicos do CLOB da Polymarket.

Responsabilidades:
- Buscar order book de um token pelo endpoint GET /book.
- Buscar order books em lote pelo endpoint POST /books.
- Calcular best_bid, best_ask, spread, mid_price e liquidez.
- Preparar snapshots para uso futuro em Redis, TimescaleDB e strategy engine.

Este módulo NÃO executa ordens.
Este módulo NÃO assina mensagens.
Este módulo NÃO usa chave privada.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class OrderLevel:
    price: float
    size: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    token_id: str
    market: str | None
    timestamp: str | None
    hash: str | None

    bids: list[OrderLevel]
    asks: list[OrderLevel]

    best_bid: float | None
    best_ask: float | None
    spread: float | None
    mid_price: float | None

    bid_depth: float
    ask_depth: float
    liquidity: float

    min_order_size: float | None
    tick_size: float | None
    neg_risk: bool | None
    last_trade_price: float | None


def decimal_to_float(value: Any) -> float | None:
    """
    Converte strings numéricas da API para float.

    A API pode retornar valores como:
    - "0.45"
    - "100"
    - 0.45
    - None
    """
    if value is None:
        return None

    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def parse_order_levels(levels: Any) -> list[OrderLevel]:
    """
    Converte bids/asks brutos da API para OrderLevel.

    Esperado:
    [
      {"price": "0.45", "size": "100"},
      {"price": "0.44", "size": "200"}
    ]
    """
    if not isinstance(levels, list):
        return []

    parsed: list[OrderLevel] = []

    for level in levels:
        if not isinstance(level, dict):
            continue

        price = decimal_to_float(level.get("price"))
        size = decimal_to_float(level.get("size"))

        if price is None or size is None:
            continue

        parsed.append(OrderLevel(price=price, size=size))

    return parsed


def calculate_best_bid(bids: list[OrderLevel]) -> float | None:
    if not bids:
        return None

    return max(level.price for level in bids)


def calculate_best_ask(asks: list[OrderLevel]) -> float | None:
    if not asks:
        return None

    return min(level.price for level in asks)


def calculate_spread(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None

    return round(best_ask - best_bid, 10)


def calculate_mid_price(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None

    return round((best_bid + best_ask) / 2, 10)


def sum_depth(levels: list[OrderLevel]) -> float:
    return round(sum(level.size for level in levels), 10)


def normalize_order_book(raw_book: dict[str, Any], token_id: str | None = None) -> OrderBookSnapshot:
    """
    Normaliza resposta bruta do CLOB para snapshot limpo.

    Campos importantes da API:
    - market
    - asset_id
    - timestamp
    - hash
    - bids
    - asks
    - min_order_size
    - tick_size
    - neg_risk
    - last_trade_price
    """
    resolved_token_id = str(
        token_id
        or raw_book.get("asset_id")
        or raw_book.get("token_id")
        or ""
    ).strip()

    if not resolved_token_id:
        raise ValueError("Order book sem token_id/asset_id")

    bids = parse_order_levels(raw_book.get("bids"))
    asks = parse_order_levels(raw_book.get("asks"))

    best_bid = calculate_best_bid(bids)
    best_ask = calculate_best_ask(asks)
    spread = calculate_spread(best_bid, best_ask)
    mid_price = calculate_mid_price(best_bid, best_ask)

    bid_depth = sum_depth(bids)
    ask_depth = sum_depth(asks)
    liquidity = round(bid_depth + ask_depth, 10)

    return OrderBookSnapshot(
        token_id=resolved_token_id,
        market=raw_book.get("market"),
        timestamp=str(raw_book.get("timestamp")) if raw_book.get("timestamp") is not None else None,
        hash=raw_book.get("hash"),
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        mid_price=mid_price,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        liquidity=liquidity,
        min_order_size=decimal_to_float(raw_book.get("min_order_size")),
        tick_size=decimal_to_float(raw_book.get("tick_size")),
        neg_risk=raw_book.get("neg_risk"),
        last_trade_price=decimal_to_float(raw_book.get("last_trade_price")),
    )


class PolymarketClobClient:
    """
    Cliente de leitura pública do CLOB.

    Endpoints usados:
    - GET /book
    - POST /books
    """

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "POLYMARKET_CLOB_BASE_URL",
            "https://clob.polymarket.com",
        ).rstrip("/")

        self.timeout_seconds = float(
            os.getenv("POLYMARKET_CLOB_REQUEST_TIMEOUT_SECONDS", "15")
        )

        self.books_batch_size = int(
            os.getenv("POLYMARKET_CLOB_BOOKS_BATCH_SIZE", "50")
        )

        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "btc-polymarket-bot/0.1",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "PolymarketClobClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def fetch_order_book_raw(self, token_id: str) -> dict[str, Any]:
        """
        Busca order book de um token.

        token_id também aparece como asset_id na resposta.
        """
        if not token_id:
            raise ValueError("token_id é obrigatório")

        response = self.client.get("/book", params={"token_id": token_id})
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError(f"Formato inesperado em /book: {type(payload)!r}")

        return payload

    def fetch_order_book(self, token_id: str) -> OrderBookSnapshot:
        raw_book = self.fetch_order_book_raw(token_id)
        return normalize_order_book(raw_book, token_id=token_id)

    def fetch_order_books_raw(self, token_ids: list[str]) -> list[dict[str, Any]]:
        """
        Busca múltiplos order books em lote via POST /books.
        """
        clean_token_ids = [token_id for token_id in token_ids if token_id]

        if not clean_token_ids:
            return []

        body = [{"token_id": token_id} for token_id in clean_token_ids]

        response = self.client.post("/books", json=body)
        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, list):
            raise ValueError(f"Formato inesperado em /books: {type(payload)!r}")

        return payload

    def fetch_order_books(self, token_ids: list[str]) -> list[OrderBookSnapshot]:
        """
        Busca múltiplos order books e normaliza os resultados.
        """
        snapshots: list[OrderBookSnapshot] = []

        for index in range(0, len(token_ids), self.books_batch_size):
            batch = token_ids[index : index + self.books_batch_size]
            raw_books = self.fetch_order_books_raw(batch)

            for raw_book in raw_books:
                snapshots.append(normalize_order_book(raw_book))

        return snapshots


def order_book_to_dict(snapshot: OrderBookSnapshot) -> dict[str, Any]:
    return {
        **asdict(snapshot),
        "bids": [asdict(level) for level in snapshot.bids],
        "asks": [asdict(level) for level in snapshot.asks],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Polymarket CLOB order book connector")
    parser.add_argument(
        "--token-id",
        default=os.getenv("POLYMARKET_CLOB_TEST_TOKEN_ID", ""),
        help="CLOB token_id / asset_id to fetch order book for",
    )

    args = parser.parse_args()

    if not args.token_id:
        print(
            "Nenhum token_id informado.\n\n"
            "Use uma das opções:\n"
            "1. python connectors\\polymarket_clob.py --token-id SEU_TOKEN_ID\n"
            "2. preencher POLYMARKET_CLOB_TEST_TOKEN_ID no .env local\n"
        )
        return

    with PolymarketClobClient() as client:
        snapshot = client.fetch_order_book(args.token_id)

    print(json.dumps(order_book_to_dict(snapshot), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()