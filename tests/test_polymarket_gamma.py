from connectors.polymarket_gamma import (
    detect_timeframe,
    normalize_market,
    parse_json_list,
)


def test_parse_json_list_from_json_string():
    assert parse_json_list('["Yes", "No"]') == ["Yes", "No"]


def test_detect_timeframe_from_explicit_15m():
    assert detect_timeframe("Bitcoin Up or Down 15 minutes") == "15m"


def test_detect_timeframe_from_time_range_15m():
    assert detect_timeframe("Bitcoin Up or Down - May 14, 3:00PM-3:15PM ET") == "15m"


def test_detect_timeframe_from_time_range_1h():
    assert detect_timeframe("Bitcoin Up or Down - May 14, 3:00PM-4:00PM ET") == "1h"


def test_normalize_market_extracts_required_fields():
    raw_market = {
        "id": "123",
        "conditionId": "0xabc",
        "question": "Bitcoin Up or Down - May 14, 3:00PM-3:15PM ET",
        "endDate": "2026-05-14T19:15:00Z",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["yes_token", "no_token"]',
    }

    market = normalize_market(raw_market)

    assert market is not None
    assert market.market_id == "123"
    assert market.condition_id == "0xabc"
    assert market.timeframe == "15m"
    assert market.yes_token_id == "yes_token"
    assert market.no_token_id == "no_token"