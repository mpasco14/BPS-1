from strategy.onchain_engine import (
    OnchainEvent,
    aggregate_onchain_events,
    calculate_many_timeframes,
    calculate_onchain_snapshot,
    get_timeframe_weight,
    normalize_onchain_event,
    normalize_timeframe,
    score_from_event,
    snapshot_to_dict,
    weight_for_event_type,
)


def test_normalize_timeframe():
    assert normalize_timeframe("5M") == "5m"
    assert normalize_timeframe("15m") == "15m"
    assert normalize_timeframe("1H") == "1h"
    assert normalize_timeframe("1D") == "1d"


def test_get_timeframe_weight():
    assert get_timeframe_weight("5m") == 0.05
    assert get_timeframe_weight("15m") == 0.10
    assert get_timeframe_weight("1h") == 0.25
    assert get_timeframe_weight("1d") == 0.40


def test_normalize_onchain_event_from_free_onchain():
    raw = {
        "source": "free_onchain",
        "provider": "mempool_space",
        "event_type": "mempool_fees",
        "asset": "BTC",
        "category": "bitcoin_network",
        "interval": "snapshot",
        "timestamp": 1000,
        "value": {"fastestFee": 50},
        "score": 0.5,
    }

    event = normalize_onchain_event(raw)

    assert event.source == "free_onchain"
    assert event.provider == "mempool_space"
    assert event.event_type == "mempool_fees"
    assert event.asset == "BTC"
    assert event.score == 0.5


def test_mempool_fees_are_bearish():
    event = OnchainEvent(
        event_type="mempool_fees",
        provider="mempool_space",
        score=0.7,
    )

    assert score_from_event(event) < 0


def test_mempool_stats_are_bearish():
    event = OnchainEvent(
        event_type="mempool_stats",
        provider="mempool_space",
        score=0.6,
    )

    assert score_from_event(event) < 0


def test_stablecoin_supply_is_mildly_bullish():
    event = OnchainEvent(
        event_type="stablecoin_supply",
        provider="defillama",
        asset="USDT",
        score=0.8,
    )

    signal = score_from_event(event)

    assert signal > 0
    assert signal <= 0.5


def test_whale_inflow_is_bearish_future_compatibility():
    event = OnchainEvent(
        event_type="whale_inflow",
        provider="premium_future",
        score=0.9,
    )

    assert score_from_event(event) < 0


def test_whale_outflow_is_bullish_future_compatibility():
    event = OnchainEvent(
        event_type="whale_outflow",
        provider="premium_future",
        score=0.9,
    )

    assert score_from_event(event) > 0


def test_weight_for_event_type():
    assert weight_for_event_type("mempool_fees") > 0
    assert weight_for_event_type("mempool_stats") > 0
    assert weight_for_event_type("stablecoin_supply") > 0
    assert weight_for_event_type("unknown") == 0


def test_aggregate_onchain_events():
    events = [
        OnchainEvent(event_type="mempool_fees", provider="mempool_space", score=0.5),
        OnchainEvent(event_type="stablecoin_supply", provider="defillama", asset="USDT", score=0.8),
    ]

    raw_score, component_signals, component_weights = aggregate_onchain_events(events)

    assert -1 <= raw_score <= 1
    assert "mempool_fees" in component_signals
    assert "stablecoin_supply" in component_signals
    assert component_weights["mempool_fees"] > 0


def test_calculate_onchain_snapshot():
    events = [
        {
            "source": "free_onchain",
            "provider": "mempool_space",
            "event_type": "mempool_fees",
            "asset": "BTC",
            "category": "bitcoin_network",
            "score": 0.5,
            "value": {"fastestFee": 50},
        },
        {
            "source": "free_onchain",
            "provider": "defillama",
            "event_type": "stablecoin_supply",
            "asset": "USDT",
            "category": "stablecoin_liquidity",
            "score": 0.8,
            "value": {"supply_usd": 100_000_000_000},
        },
    ]

    snapshot = calculate_onchain_snapshot(
        timeframe="1h",
        events=events,
        symbol="BTCUSDT",
    )

    assert snapshot.source == "onchain_engine"
    assert snapshot.venue == "binance_futures"
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.timeframe == "1h"
    assert snapshot.event_count == 2
    assert snapshot.is_ready is True
    assert -1 <= snapshot.raw_onchain_score <= 1
    assert -1 <= snapshot.onchain_score <= 1
    assert snapshot.timeframe_weight == 0.25


def test_calculate_many_timeframes():
    events = [
        {
            "event_type": "stablecoin_supply",
            "provider": "defillama",
            "asset": "USDT",
            "score": 0.8,
        }
    ]

    snapshots = calculate_many_timeframes(events, symbol="BTCUSDT")

    assert set(snapshots.keys()) == {"5m", "15m", "1h", "1d"}
    assert snapshots["5m"].timeframe_weight == 0.05
    assert snapshots["1d"].timeframe_weight == 0.40


def test_snapshot_to_dict():
    snapshot = calculate_onchain_snapshot(
        timeframe="5m",
        events=[
            {
                "event_type": "mempool_fees",
                "provider": "mempool_space",
                "score": 0.5,
            }
        ],
    )

    payload = snapshot_to_dict(snapshot)

    assert payload["source"] == "onchain_engine"
    assert payload["timeframe"] == "5m"
    assert "onchain_score" in payload