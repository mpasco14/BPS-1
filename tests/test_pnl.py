import pytest

from accounting.pnl import (
    build_equity_curve,
    calculate_gross_pnl,
    calculate_max_drawdown,
    calculate_trade_pnl,
    summarize_pnl,
)


def test_calculate_gross_pnl_long():
    assert calculate_gross_pnl(
        side="LONG",
        entry_price=60000,
        exit_price=60210,
        quantity=0.01,
    ) == pytest.approx(2.10)


def test_calculate_gross_pnl_short():
    assert calculate_gross_pnl(
        side="SHORT",
        entry_price=60000,
        exit_price=59790,
        quantity=0.01,
    ) == pytest.approx(2.10)


def test_calculate_trade_pnl_net_profit():
    pnl = calculate_trade_pnl(
        side="LONG",
        entry_price=60000,
        exit_price=60210,
        quantity=0.01,
        margin_usd=20,
        notional_usd=600,
        fees_usd=0.10,
    )

    assert pnl.gross_pnl_usd == pytest.approx(2.10)
    assert pnl.net_pnl_usd == pytest.approx(2.00)
    assert pnl.return_on_margin_pct == pytest.approx(0.10)
    assert pnl.is_win is True


def test_calculate_trade_pnl_loss():
    pnl = calculate_trade_pnl(
        side="LONG",
        entry_price=60000,
        exit_price=59895,
        quantity=0.01,
        margin_usd=20,
        notional_usd=600,
        fees_usd=0.10,
    )

    assert pnl.gross_pnl_usd == pytest.approx(-1.05)
    assert pnl.net_pnl_usd == pytest.approx(-1.15)
    assert pnl.is_win is False


def test_build_equity_curve():
    curve = build_equity_curve(
        initial_balance_usd=100,
        pnl_values=[2, -1, 3],
    )

    assert curve == [100, 102, 101, 104]


def test_calculate_max_drawdown():
    drawdown_usd, drawdown_pct = calculate_max_drawdown([100, 105, 101, 110])

    assert drawdown_usd == pytest.approx(4)
    assert drawdown_pct == pytest.approx(4 / 105)


def test_summarize_pnl():
    trades = [
        calculate_trade_pnl(
            side="LONG",
            entry_price=60000,
            exit_price=60210,
            quantity=0.01,
            margin_usd=20,
            fees_usd=0.10,
        ),
        calculate_trade_pnl(
            side="LONG",
            entry_price=60000,
            exit_price=59895,
            quantity=0.01,
            margin_usd=20,
            fees_usd=0.10,
        ),
    ]

    summary = summarize_pnl(trades, initial_balance_usd=100)

    assert summary.trade_count == 2
    assert summary.wins == 1
    assert summary.losses == 1
    assert summary.net_pnl_usd == pytest.approx(0.85)
    assert summary.win_rate == pytest.approx(0.5)
    assert summary.profit_factor is not None