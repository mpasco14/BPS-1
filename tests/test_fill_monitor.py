from risk.exposure import default_exposure_snapshot
from execution.fill_monitor import (
    apply_fill_update_to_exposure,
    decide_partial_fill_action,
    fill_ratio,
    is_full_fill,
    is_partial_fill,
    normalize_order_trade_update,
)


def sample_event(status="PARTIALLY_FILLED", cumulative="0.006", last="0.006"):
    return {
        "e": "ORDER_TRADE_UPDATE",
        "E": 123,
        "T": 124,
        "o": {
            "s": "BTCUSDT",
            "c": "client-1",
            "i": 12345,
            "S": "BUY",
            "o": "LIMIT",
            "x": "TRADE",
            "X": status,
            "q": "0.010",
            "l": last,
            "z": cumulative,
            "L": "60000",
            "ap": "60000",
            "N": "USDT",
            "n": "0.01",
            "rp": "0",
        },
    }


def test_normalize_order_trade_update():
    update = normalize_order_trade_update(sample_event())

    assert update.event_type == "ORDER_TRADE_UPDATE"
    assert update.symbol == "BTCUSDT"
    assert update.client_order_id == "client-1"
    assert update.order_status == "PARTIALLY_FILLED"
    assert update.cumulative_filled_qty == 0.006


def test_partial_fill_decision_keep_rest():
    update = normalize_order_trade_update(sample_event())

    decision = decide_partial_fill_action(update, edge_valid=True)

    assert is_partial_fill(update) is True
    assert fill_ratio(update) == 0.6
    assert decision.action == "KEEP_REST"


def test_partial_fill_decision_cancel_rest_when_edge_lost():
    update = normalize_order_trade_update(sample_event())

    decision = decide_partial_fill_action(update, edge_valid=False)

    assert decision.action == "CANCEL_REST"


def test_full_fill_detection():
    update = normalize_order_trade_update(
        sample_event(status="FILLED", cumulative="0.010", last="0.004")
    )

    assert is_full_fill(update) is True


def test_apply_fill_update_to_exposure():
    snapshot = default_exposure_snapshot()
    update = normalize_order_trade_update(sample_event())

    updated = apply_fill_update_to_exposure(
        snapshot,
        update,
        timeframe="5m",
        leverage=30,
    )

    assert updated.open_positions == 1
    assert updated.exposure_per_market["BTCUSDT"] > 0