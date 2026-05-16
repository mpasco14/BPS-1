from risk.risk_manager import calculate_order_plan
from tests.test_risk_manager import custom_profile

from accounting.positions import (
    PositionBook,
    build_position_from_order_plan,
    calculate_unrealized_pnl,
    check_exit_condition,
)


def sample_plan(direction="LONG"):
    return calculate_order_plan(
        direction=direction,
        entry_price=60000,
        timeframe="5m",
        profile=custom_profile(),
    )


def test_build_position_from_order_plan():
    position = build_position_from_order_plan(
        sample_plan("LONG"),
        entry_fee_usd=0.05,
        position_id="pos-1",
    )

    assert position.position_id == "pos-1"
    assert position.side == "LONG"
    assert position.entry_price == 60000
    assert position.status == "OPEN"


def test_calculate_unrealized_pnl_long():
    position = build_position_from_order_plan(sample_plan("LONG"))

    pnl = calculate_unrealized_pnl(position, mark_price=60210)

    assert round(pnl, 2) == 2.10


def test_calculate_unrealized_pnl_short():
    position = build_position_from_order_plan(sample_plan("SHORT"))

    pnl = calculate_unrealized_pnl(position, mark_price=59790)

    assert round(pnl, 2) == 2.10


def test_check_exit_condition_long_tp():
    position = build_position_from_order_plan(sample_plan("LONG"))

    assert check_exit_condition(position, 60210) == "take_profit"


def test_check_exit_condition_long_sl():
    position = build_position_from_order_plan(sample_plan("LONG"))

    assert check_exit_condition(position, 59895) == "stop_loss"


def test_position_book_open_and_close():
    book = PositionBook()
    position = book.open_from_order_plan(
        sample_plan("LONG"),
        entry_fee_usd=0.05,
        position_id="pos-1",
    )

    assert book.open_count() == 1

    closed = book.close(
        position.position_id,
        exit_price=60210,
        reason="take_profit",
        exit_fee_usd=0.05,
    )

    assert closed.status == "CLOSED"
    assert round(closed.gross_pnl_usd, 2) == 2.10
    assert round(closed.realized_pnl_usd, 2) == 2.00
    assert book.open_count() == 0
    assert book.closed_count() == 1