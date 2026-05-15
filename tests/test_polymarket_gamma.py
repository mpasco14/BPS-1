from connectors.polymarket_gamma import (
    detect_timeframe,
    is_active_tradeable_market,
    looks_like_bitcoin_market,
    normalize_market,
    parse_json_list,
)


def test_parse_json_list_from_json_string():
    assert parse_json_list('["Yes", "No"]') == ["Yes", "No"]


def test_parse_json_list_from_list():
    assert parse_json_list(["Yes", "No"]) == ["Yes", "No"]


def test_detect_timeframe_from_explicit_15m():
    assert detect_timeframe("Bitcoin Up or Down 15 minutes") == "15m"


def test_detect_timeframe_from_time_range_15m():
    assert detect_timeframe("Bitcoin Up or Down - May 14, 3:00PM-3:15PM ET") == "15m"


def test_detect_timeframe_from_time_range_1h():
    assert detect_timeframe("Bitcoin Up or Down - May 14, 3:00PM-4:00PM ET") == "1h"


def test_detect_timeframe_from_daily_word():
    assert detect_timeframe("Will Bitcoin close higher today?") == "1d"


def test_looks_like_bitcoin_market_from_market_question():
    raw_market = {
        "question": "Bitcoin Up or Down - May 14, 3:00PM-3:15PM ET",
    }

    assert looks_like_bitcoin_market(raw_market)


def test_looks_like_bitcoin_market_from_event_title():
    raw_market = {
        "question": "Up or Down - May 14, 3:00PM-3:15PM ET",
    }

    event = {
        "title": "Bitcoin price markets",
        "slug": "bitcoin-price-markets",
    }

    assert looks_like_bitcoin_market(raw_market, event=event)


def test_is_active_tradeable_market_rejects_closed_market():
    raw_market = {
        "active": True,
        "closed": True,
        "enableOrderBook": True,
        "acceptingOrders": True,
    }

    assert not is_active_tradeable_market(raw_market)


def test_is_active_tradeable_market_accepts_valid_market():
    raw_market = {
        "active": True,
        "closed": False,
        "archived": False,
        "enableOrderBook": True,
        "acceptingOrders": True,
    }

    assert is_active_tradeable_market(raw_market)


def test_normalize_market_extracts_required_fields():
    raw_market = {
        "id": "123",
        "conditionId": "0xabc",
        "question": "Bitcoin Up or Down - May 14, 3:00PM-3:15PM ET",
        "endDate": "2026-05-14T19:15:00Z",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["yes_token", "no_token"]',
        "slug": "bitcoin-up-or-down-test",
    }

    event = {
        "id": "event_1",
        "slug": "bitcoin-event",
        "title": "Bitcoin event",
    }

    market = normalize_market(raw_market, event=event, source_endpoint="events")

    assert market is not None
    assert market.market_id == "123"
    assert market.condition_id == "0xabc"
    assert market.timeframe == "15m"
    assert market.yes_token_id == "yes_token"
    assert market.no_token_id == "no_token"
    assert market.event_id == "event_1"
    assert market.event_slug == "bitcoin-event"
    assert market.event_title == "Bitcoin event"
    assert market.source_endpoint == "events"