import json
from datetime import datetime, timezone

import pytest

from data.feature_store import (
    FeatureSnapshot,
    build_create_table_sql,
    build_feature_snapshot,
    build_insert_sql,
    calculate_combined_score,
    parse_table_name,
    qualified_table_name,
    record_to_insert_values,
    snapshot_to_record,
    timestamp_to_utc_datetime,
)


def sample_technical():
    return {
        "source": "technical_engine",
        "venue": "binance_futures",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "latest_close": 60000.0,
        "latest_open_time": "2026-05-15T18:00:00+00:00",
        "latest_close_time": "2026-05-15T18:04:59+00:00",
        "technical_score": 0.4,
        "indicators": {
            "funding_rate": 0.0001,
            "open_interest": 100000.0,
            "mark_price": 60000.5,
            "index_price": 60001.0,
        },
        "signals": {
            "ema_signal": 0.5,
        },
    }


def sample_orderbook():
    return {
        "source": "orderbook_engine",
        "venue": "binance_futures",
        "symbol": "BTCUSDT",
        "spread_pct": 0.0001,
        "bid_depth_notional": 150000.0,
        "ask_depth_notional": 120000.0,
        "microstructure_score": 0.2,
        "is_tradeable": True,
    }


def sample_onchain():
    return {
        "source": "onchain_engine",
        "venue": "binance_futures",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "onchain_score": 0.03,
    }


def sample_sentiment():
    return {
        "source": "sentiment_engine",
        "venue": "binance_futures",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "sentiment_score": 0.02,
    }


def test_timestamp_to_utc_datetime_from_iso():
    result = timestamp_to_utc_datetime("2026-05-15T18:00:00+00:00")

    assert result.tzinfo is not None
    assert result.year == 2026


def test_timestamp_to_utc_datetime_from_milliseconds():
    result = timestamp_to_utc_datetime(1_000_000_000_000)

    assert result == datetime.fromtimestamp(1_000_000_000, tz=timezone.utc)


def test_calculate_combined_score():
    score = calculate_combined_score(
        tech_score=0.4,
        microstructure_score=0.2,
        onchain_score=0.1,
        sentiment_score=0.1,
    )

    assert -1 <= score <= 1
    assert score > 0


def test_feature_snapshot_validation():
    snapshot = FeatureSnapshot(
        timestamp="2026-05-15T18:00:00+00:00",
        venue="binance_futures",
        instrument_id="btcusdt",
        symbol="btcusdt",
        timeframe="5M",
        tech_score=0.4,
        onchain_score=0.1,
        sentiment_score=0.1,
        microstructure_score=0.2,
        combined_score=0.3,
    )

    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.instrument_id == "BTCUSDT"
    assert snapshot.timeframe == "5m"


def test_feature_snapshot_rejects_invalid_score():
    with pytest.raises(ValueError):
        FeatureSnapshot(
            timeframe="5m",
            tech_score=2.0,
            combined_score=0.0,
        )


def test_build_feature_snapshot():
    snapshot = build_feature_snapshot(
        timeframe="5m",
        technical=sample_technical(),
        orderbook=sample_orderbook(),
        onchain=sample_onchain(),
        sentiment=sample_sentiment(),
        symbol="BTCUSDT",
    )

    assert snapshot.venue == "binance_futures"
    assert snapshot.instrument_id == "BTCUSDT"
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.timeframe == "5m"
    assert snapshot.tech_score == 0.4
    assert snapshot.microstructure_score == 0.2
    assert snapshot.onchain_score == 0.03
    assert snapshot.sentiment_score == 0.02
    assert snapshot.binance_spread_pct == 0.0001
    assert snapshot.binance_liquidity_usd == 120000.0
    assert snapshot.funding_rate == 0.0001
    assert -1 <= snapshot.combined_score <= 1


def test_build_feature_snapshot_supports_nested_orderbook_analysis():
    orderbook_event = {
        "event_type": "orderbook_microstructure",
        "analysis": sample_orderbook(),
    }

    snapshot = build_feature_snapshot(
        timeframe="5m",
        technical=sample_technical(),
        orderbook=orderbook_event,
    )

    assert snapshot.microstructure_score == 0.2
    assert snapshot.binance_spread_pct == 0.0001


def test_snapshot_to_record_serializes_json_fields():
    snapshot = build_feature_snapshot(
        timeframe="5m",
        technical=sample_technical(),
        orderbook=sample_orderbook(),
        onchain=sample_onchain(),
        sentiment=sample_sentiment(),
    )

    record = snapshot_to_record(snapshot)

    assert isinstance(record["btc_features"], str)
    assert isinstance(record["raw_components"], str)

    decoded = json.loads(record["btc_features"])

    assert "technical" in decoded
    assert "orderbook" in decoded


def test_parse_table_name():
    assert parse_table_name("market_data.feature_snapshots") == (
        "market_data",
        "feature_snapshots",
    )

    assert parse_table_name("feature_snapshots") == (
        "public",
        "feature_snapshots",
    )


def test_qualified_table_name():
    assert qualified_table_name("market_data.feature_snapshots") == "market_data.feature_snapshots"


def test_build_create_table_sql():
    statements = build_create_table_sql("market_data.feature_snapshots")

    joined = "\n".join(statements)

    assert "CREATE TABLE IF NOT EXISTS market_data.feature_snapshots" in joined
    assert "combined_score" in joined
    assert "btc_features JSONB" in joined


def test_build_insert_sql():
    sql = build_insert_sql("market_data.feature_snapshots")

    assert "INSERT INTO market_data.feature_snapshots" in sql
    assert "ON CONFLICT" in sql


def test_record_to_insert_values_length():
    snapshot = build_feature_snapshot(
        timeframe="5m",
        technical=sample_technical(),
    )

    record = snapshot_to_record(snapshot)
    values = record_to_insert_values(record)

    assert len(values) > 0
    assert len(values) == 23