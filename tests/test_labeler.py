import pytest

from models.labeler import (
    calculate_barrier_prices,
    label_price_path,
    timestamp_to_seconds,
)


def test_timestamp_to_seconds():
    assert timestamp_to_seconds(1000) == 1000
    assert timestamp_to_seconds(1_000_000_000_000) == 1_000_000_000
    assert timestamp_to_seconds("1000") == 1000
    assert timestamp_to_seconds("2026-05-15T18:00:00+00:00") is not None


def test_calculate_barrier_prices_long():
    tp, sl = calculate_barrier_prices(
        side="LONG",
        entry_price=60000,
        tp_move_pct=2.10 / 600,
        sl_move_pct=1.05 / 600,
    )

    assert tp == pytest.approx(60210)
    assert sl == pytest.approx(59895)


def test_calculate_barrier_prices_short():
    tp, sl = calculate_barrier_prices(
        side="SHORT",
        entry_price=60000,
        tp_move_pct=2.10 / 600,
        sl_move_pct=1.05 / 600,
    )

    assert tp == pytest.approx(59790)
    assert sl == pytest.approx(60105)


def test_label_long_take_profit():
    label = label_price_path(
        side="LONG",
        entry_price=60000,
        take_profit_price=60210,
        stop_loss_price=59895,
        quantity=0.01,
        price_path=[
            {"timestamp": 1, "high": 60210, "low": 60000, "close": 60210},
        ],
    )

    assert label.outcome == "take_profit"
    assert label.target == 1
    assert label.gross_pnl_usd == pytest.approx(2.10)


def test_label_long_stop_loss():
    label = label_price_path(
        side="LONG",
        entry_price=60000,
        take_profit_price=60210,
        stop_loss_price=59895,
        quantity=0.01,
        price_path=[
            {"timestamp": 1, "high": 60050, "low": 59895, "close": 59895},
        ],
    )

    assert label.outcome == "stop_loss"
    assert label.target == 0
    assert label.gross_pnl_usd == pytest.approx(-1.05)


def test_label_short_take_profit():
    label = label_price_path(
        side="SHORT",
        entry_price=60000,
        take_profit_price=59790,
        stop_loss_price=60105,
        quantity=0.01,
        price_path=[
            {"timestamp": 1, "high": 60000, "low": 59790, "close": 59790},
        ],
    )

    assert label.outcome == "take_profit"
    assert label.target == 1
    assert label.gross_pnl_usd == pytest.approx(2.10)


def test_ambiguous_same_bar_defaults_to_stop_loss():
    label = label_price_path(
        side="LONG",
        entry_price=60000,
        take_profit_price=60210,
        stop_loss_price=59895,
        quantity=0.01,
        conservative_on_ambiguous=True,
        price_path=[
            {"timestamp": 1, "high": 60210, "low": 59895, "close": 60000},
        ],
    )

    assert label.ambiguous_same_bar is True
    assert label.outcome == "stop_loss"
    assert label.target == 0


def test_time_barrier_when_no_tp_or_sl():
    label = label_price_path(
        side="LONG",
        entry_price=60000,
        take_profit_price=60210,
        stop_loss_price=59895,
        quantity=0.01,
        price_path=[
            {"timestamp": 1, "high": 60050, "low": 59950, "close": 60025},
        ],
    )

    assert label.outcome == "time_barrier"
    assert label.target is None
    assert label.exit_price == 60025