from risk.exposure import (
    apply_close_to_exposure,
    apply_fill_to_exposure,
    default_exposure_snapshot,
    exposure_pct,
    snapshot_from_json,
    snapshot_to_json,
)


def test_default_exposure_snapshot():
    snapshot = default_exposure_snapshot()

    assert snapshot.total_bankroll_usd > 0
    assert snapshot.open_positions == 0


def test_apply_fill_to_exposure_long():
    snapshot = default_exposure_snapshot()

    updated = apply_fill_to_exposure(
        snapshot,
        symbol="BTCUSDT",
        timeframe="5m",
        direction="LONG",
        margin_usd=20,
    )

    assert updated.open_positions == 1
    assert updated.exposure_per_market["BTCUSDT"] == 20
    assert updated.exposure_by_timeframe["5m"] == 20
    assert updated.btc_directional_exposure_usd == 20


def test_apply_close_to_exposure():
    snapshot = default_exposure_snapshot()
    snapshot = apply_fill_to_exposure(
        snapshot,
        symbol="BTCUSDT",
        timeframe="5m",
        direction="LONG",
        margin_usd=20,
    )

    updated = apply_close_to_exposure(
        snapshot,
        symbol="BTCUSDT",
        timeframe="5m",
        direction="LONG",
        margin_usd=20,
        realized_pnl_usd=2,
    )

    assert updated.open_positions == 0
    assert updated.daily_pnl_usd == 2
    assert updated.exposure_per_market["BTCUSDT"] == 0
    assert updated.btc_directional_exposure_usd == 0


def test_snapshot_json_roundtrip():
    snapshot = default_exposure_snapshot()
    payload = snapshot_to_json(snapshot)
    loaded = snapshot_from_json(payload)

    assert loaded.total_bankroll_usd == snapshot.total_bankroll_usd


def test_exposure_pct():
    snapshot = default_exposure_snapshot()
    snapshot.total_bankroll_usd = 1000

    assert exposure_pct(snapshot, 50) == 0.05