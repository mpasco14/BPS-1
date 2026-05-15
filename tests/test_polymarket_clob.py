from connectors.polymarket_clob import (
    calculate_best_ask,
    calculate_best_bid,
    calculate_mid_price,
    calculate_spread,
    normalize_order_book,
    parse_order_levels,
)


def test_parse_order_levels():
    levels = [
        {"price": "0.45", "size": "100"},
        {"price": "0.44", "size": "200"},
    ]

    parsed = parse_order_levels(levels)

    assert len(parsed) == 2
    assert parsed[0].price == 0.45
    assert parsed[0].size == 100


def test_calculate_best_bid():
    bids = parse_order_levels(
        [
            {"price": "0.42", "size": "100"},
            {"price": "0.45", "size": "100"},
            {"price": "0.44", "size": "100"},
        ]
    )

    assert calculate_best_bid(bids) == 0.45


def test_calculate_best_ask():
    asks = parse_order_levels(
        [
            {"price": "0.48", "size": "100"},
            {"price": "0.46", "size": "100"},
            {"price": "0.47", "size": "100"},
        ]
    )

    assert calculate_best_ask(asks) == 0.46


def test_calculate_spread():
    assert calculate_spread(0.54, 0.56) == 0.02


def test_calculate_mid_price():
    assert calculate_mid_price(0.54, 0.56) == 0.55


def test_normalize_order_book():
    raw_book = {
        "market": "0xmarket",
        "asset_id": "token_yes",
        "timestamp": "1234567890",
        "hash": "abc123",
        "bids": [
            {"price": "0.54", "size": "100"},
            {"price": "0.53", "size": "200"},
        ],
        "asks": [
            {"price": "0.56", "size": "150"},
            {"price": "0.57", "size": "250"},
        ],
        "min_order_size": "5",
        "tick_size": "0.01",
        "neg_risk": False,
        "last_trade_price": "0.55",
    }

    snapshot = normalize_order_book(raw_book)

    assert snapshot.token_id == "token_yes"
    assert snapshot.market == "0xmarket"
    assert snapshot.best_bid == 0.54
    assert snapshot.best_ask == 0.56
    assert snapshot.spread == 0.02
    assert snapshot.mid_price == 0.55
    assert snapshot.bid_depth == 300
    assert snapshot.ask_depth == 400
    assert snapshot.liquidity == 700
    assert snapshot.min_order_size == 5
    assert snapshot.tick_size == 0.01
    assert snapshot.last_trade_price == 0.55


def test_normalize_order_book_with_empty_side():
    raw_book = {
        "market": "0xmarket",
        "asset_id": "token_yes",
        "timestamp": "1234567890",
        "hash": "abc123",
        "bids": [],
        "asks": [],
    }

    snapshot = normalize_order_book(raw_book)

    assert snapshot.best_bid is None
    assert snapshot.best_ask is None
    assert snapshot.spread is None
    assert snapshot.mid_price is None
    assert snapshot.liquidity == 0