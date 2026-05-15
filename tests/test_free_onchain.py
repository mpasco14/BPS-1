from connectors.free_onchain import (
    FreeOnchainEvent,
    calculate_fee_pressure_score,
    calculate_mempool_congestion_score,
    clamp_score,
    event_to_kafka,
    normalize_mempool_event,
    normalize_stablecoin_event,
    parse_bool,
    parse_csv_env,
    safe_float,
)


def test_parse_bool():
    assert parse_bool("true") is True
    assert parse_bool("1") is True
    assert parse_bool("yes") is True
    assert parse_bool("false") is False
    assert parse_bool(None, default=True) is True


def test_parse_csv_env():
    assert parse_csv_env("USDT, USDC,DAI") == ["USDT", "USDC", "DAI"]


def test_safe_float():
    assert safe_float("1.23") == 1.23
    assert safe_float(10) == 10.0
    assert safe_float(None) is None
    assert safe_float("not-a-number") is None


def test_clamp_score():
    assert clamp_score(-1) == 0.0
    assert clamp_score(0.5) == 0.5
    assert clamp_score(2) == 1.0


def test_calculate_fee_pressure_score():
    fees = {
        "fastestFee": 50,
        "halfHourFee": 30,
        "hourFee": 20,
        "economyFee": 10,
        "minimumFee": 5,
    }

    assert calculate_fee_pressure_score(fees) == 0.5


def test_calculate_mempool_congestion_score():
    mempool_stats = {
        "count": 10000,
        "vsize": 150_000_000,
        "total_fee": 123456789,
        "fee_histogram": [],
    }

    assert calculate_mempool_congestion_score(mempool_stats) == 0.5


def test_normalize_mempool_event():
    event = normalize_mempool_event(
        event_type="mempool_fees",
        value={
            "fastestFee": 50,
            "halfHourFee": 30,
            "hourFee": 20,
            "economyFee": 10,
            "minimumFee": 5,
        },
        score=0.5,
    )

    assert event.source == "free_onchain"
    assert event.provider == "mempool_space"
    assert event.asset == "BTC"
    assert event.category == "bitcoin_network"
    assert event.event_type == "mempool_fees"
    assert event.score == 0.5


def test_normalize_stablecoin_event():
    event = normalize_stablecoin_event(
        stablecoin_symbol="USDT",
        value={
            "id": 1,
            "name": "Tether",
            "symbol": "USDT",
            "circulating": {"peggedUSD": 100000000000},
        },
    )

    assert event.source == "free_onchain"
    assert event.provider == "defillama"
    assert event.asset == "USDT"
    assert event.category == "stablecoin_liquidity"
    assert event.event_type == "stablecoin_supply"


def test_event_to_kafka():
    event = FreeOnchainEvent(
        source="free_onchain",
        provider="mempool_space",
        event_type="mempool_fees",
        asset="BTC",
        category="bitcoin_network",
        interval="snapshot",
        timestamp=1000,
        collected_at="2026-05-15T00:00:00+00:00",
        value={"fastestFee": 50},
        raw={"fastestFee": 50},
        score=0.5,
    )

    kafka_event = event_to_kafka(event, topic="onchain-events")

    assert kafka_event.topic == "onchain-events"
    assert kafka_event.key == "BTC:mempool_fees:snapshot:1000"
    assert kafka_event.value["asset"] == "BTC"
    assert kafka_event.value["event_type"] == "mempool_fees"