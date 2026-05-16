import asyncio
import json

import pytest

from connectors.binance_orderbook_ws import (
    BinanceOrderbookWsConnector,
    build_orderbook_stream_name,
    build_orderbook_ws_url,
    normalize_depth_levels,
    normalize_orderbook_ws_payload,
    normalize_update_speed,
    orderbook_analysis_to_kafka,
    unwrap_stream_message,
)


def sample_ws_payload():
    return {
        "e": "depthUpdate",
        "E": 1571889248277,
        "T": 1571889248276,
        "s": "BTCUSDT",
        "U": 390497796,
        "u": 390497878,
        "pu": 390497794,
        "b": [
            ["59999.0", "2.0"],
            ["59998.0", "1.5"],
            ["59997.0", "1.0"],
            ["59996.0", "1.0"],
            ["59995.0", "1.0"],
        ],
        "a": [
            ["60001.0", "1.0"],
            ["60002.0", "1.5"],
            ["60003.0", "1.0"],
            ["60004.0", "1.0"],
            ["60005.0", "1.0"],
        ],
    }


def test_normalize_depth_levels():
    assert normalize_depth_levels(5) == 5
    assert normalize_depth_levels("10") == 10

    with pytest.raises(ValueError):
        normalize_depth_levels(50)


def test_normalize_update_speed():
    assert normalize_update_speed("100ms") == "100ms"
    assert normalize_update_speed("500ms") == "500ms"
    assert normalize_update_speed("250ms") == ""
    assert normalize_update_speed("") == ""

    with pytest.raises(ValueError):
        normalize_update_speed("1s")


def test_build_orderbook_stream_name():
    stream = build_orderbook_stream_name(
        symbol="BTCUSDT",
        depth_levels=5,
        update_speed="100ms",
    )

    assert stream == "btcusdt@depth5@100ms"


def test_build_orderbook_ws_url():
    url = build_orderbook_ws_url(
        base_url="wss://fstream.binance.com/public",
        symbol="BTCUSDT",
        depth_levels=5,
        update_speed="100ms",
    )

    assert url == "wss://fstream.binance.com/public/ws/btcusdt@depth5@100ms"


def test_unwrap_stream_message_direct():
    payload = sample_ws_payload()

    assert unwrap_stream_message(payload) == payload


def test_unwrap_stream_message_combined():
    payload = {
        "stream": "btcusdt@depth5@100ms",
        "data": sample_ws_payload(),
    }

    assert unwrap_stream_message(payload) == sample_ws_payload()


def test_normalize_orderbook_ws_payload():
    event = normalize_orderbook_ws_payload(sample_ws_payload())

    assert event["source"] == "binance_orderbook_ws"
    assert event["venue"] == "binance_futures"
    assert event["symbol"] == "BTCUSDT"
    assert event["event_type"] == "depthUpdate"
    assert event["final_update_id"] == 390497878
    assert len(event["b"]) == 5
    assert len(event["a"]) == 5


def test_orderbook_analysis_to_kafka():
    analysis = {
        "symbol": "BTCUSDT",
        "spread_pct": 0.0001,
        "microstructure_score": 0.1,
        "is_tradeable": True,
    }

    raw_event = normalize_orderbook_ws_payload(sample_ws_payload())

    event = orderbook_analysis_to_kafka(
        analysis=analysis,
        raw_event=raw_event,
        topic="binance-orderbook",
    )

    assert event.topic == "binance-orderbook"
    assert event.key.startswith("BTCUSDT:orderbook:")
    assert event.value["event_type"] == "orderbook_microstructure"
    assert event.value["analysis"]["symbol"] == "BTCUSDT"


def test_connector_handle_raw_message_without_publish():
    async def run_test():
        connector = BinanceOrderbookWsConnector(
            symbol="BTCUSDT",
            depth_levels=5,
            update_speed="100ms",
            publish_to_kafka=False,
        )

        result = await connector._handle_raw_message(json.dumps(sample_ws_payload()))

        assert result is not None
        assert result["symbol"] == "BTCUSDT"
        assert result["best_bid"] == 59999.0
        assert result["best_ask"] == 60001.0
        assert -1 <= result["microstructure_score"] <= 1

    asyncio.run(run_test())


def test_connector_ws_url():
    connector = BinanceOrderbookWsConnector(
        symbol="BTCUSDT",
        depth_levels=5,
        update_speed="100ms",
        publish_to_kafka=False,
    )

    assert connector.ws_url().endswith("/ws/btcusdt@depth5@100ms")