from connectors.polymarket_ws import (
    calculate_best_ask_from_levels,
    calculate_best_bid_from_levels,
    calculate_spread,
    normalize_market_ws_message,
    normalized_market_event_to_kafka,
    parse_csv_env,
)


def test_parse_csv_env():
    assert parse_csv_env("a,b, c") == ["a", "b", "c"]


def test_calculate_best_bid_from_levels():
    levels = [
        {"price": "0.48", "size": "30"},
        {"price": "0.49", "size": "20"},
        {"price": "0.50", "size": "15"},
    ]

    assert calculate_best_bid_from_levels(levels) == 0.5


def test_calculate_best_ask_from_levels():
    levels = [
        {"price": "0.52", "size": "25"},
        {"price": "0.53", "size": "60"},
        {"price": "0.54", "size": "10"},
    ]

    assert calculate_best_ask_from_levels(levels) == 0.52


def test_calculate_spread():
    assert calculate_spread(0.48, 0.52) == 0.04


def test_normalize_book_message():
    message = {
        "event_type": "book",
        "asset_id": "token_yes",
        "market": "0xmarket",
        "bids": [
            {"price": ".48", "size": "30"},
            {"price": ".49", "size": "20"},
        ],
        "asks": [
            {"price": ".52", "size": "25"},
            {"price": ".53", "size": "60"},
        ],
        "timestamp": "123456789000",
        "hash": "0xabc",
    }

    events = normalize_market_ws_message(message)

    assert len(events) == 1
    assert events[0].event_type == "book"
    assert events[0].asset_id == "token_yes"
    assert events[0].market == "0xmarket"
    assert events[0].best_bid == 0.49
    assert events[0].best_ask == 0.52
    assert events[0].spread == 0.03


def test_normalize_price_change_message():
    message = {
        "market": "0xmarket",
        "price_changes": [
            {
                "asset_id": "token_yes",
                "price": "0.5",
                "size": "200",
                "side": "BUY",
                "best_bid": "0.5",
                "best_ask": "1",
            },
            {
                "asset_id": "token_no",
                "price": "0.5",
                "size": "200",
                "side": "SELL",
                "best_bid": "0",
                "best_ask": "0.5",
            },
        ],
        "timestamp": "1757908892351",
        "event_type": "price_change",
    }

    events = normalize_market_ws_message(message)

    assert len(events) == 2
    assert events[0].asset_id == "token_yes"
    assert events[0].best_bid == 0.5
    assert events[0].best_ask == 1.0
    assert events[0].spread == 0.5


def test_normalize_best_bid_ask_message():
    message = {
        "event_type": "best_bid_ask",
        "market": "0xmarket",
        "asset_id": "token_yes",
        "best_bid": "0.73",
        "best_ask": "0.77",
        "spread": "0.04",
        "timestamp": "1766789469958",
    }

    events = normalize_market_ws_message(message)

    assert len(events) == 1
    assert events[0].event_type == "best_bid_ask"
    assert events[0].best_bid == 0.73
    assert events[0].best_ask == 0.77
    assert events[0].spread == 0.04


def test_normalized_market_event_to_kafka():
    message = {
        "event_type": "best_bid_ask",
        "market": "0xmarket",
        "asset_id": "token_yes",
        "best_bid": "0.73",
        "best_ask": "0.77",
        "spread": "0.04",
        "timestamp": "1766789469958",
    }

    event = normalize_market_ws_message(message)[0]
    kafka_event = normalized_market_event_to_kafka(event, topic="poly-orderbook")

    assert kafka_event.topic == "poly-orderbook"
    assert kafka_event.key == "0xmarket:token_yes:best_bid_ask"
    assert kafka_event.value["event_type"] == "best_bid_ask"