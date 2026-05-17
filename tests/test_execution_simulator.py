import pytest

from backtesting.execution_simulator import simulate_execution
from risk.risk_manager import RiskProfile, calculate_order_plan


def custom_profile():
    return RiskProfile(
        venue="binance_futures",
        symbol="BTCUSDT",
        margin_usd=20,
        leverage=30,
        notional_usd=600,
        gross_take_profit_usd=2.10,
        gross_stop_loss_usd=1.05,
        estimated_entry_fee_usd=0.05,
        estimated_exit_fee_usd=0.05,
        max_leverage=30,
        max_margin_usd=20,
        max_notional_usd=600,
        max_daily_loss_usd=5,
        max_trade_loss_usd=1.05,
        max_consecutive_losses=3,
        max_open_positions=1,
        max_open_orders=3,
        max_spread_pct=0.002,
        min_liquidity_usd=50000,
        min_confidence=0.65,
    )


def sample_plan(direction="LONG"):
    return calculate_order_plan(
        direction=direction,
        entry_price=60000,
        timeframe="5m",
        profile=custom_profile(),
    )


def test_simulate_long_take_profit():
    result = simulate_execution(
        order_plan=sample_plan("LONG"),
        slippage_pct=0.0,
        entry_fee_usd=0.05,
        exit_fee_usd=0.05,
        price_path=[
            {"timestamp": 1, "high": 60210, "low": 60000, "close": 60210},
        ],
    )

    assert result.outcome == "take_profit"
    assert result.target == 1
    assert result.pnl["net_pnl_usd"] == pytest.approx(2.00)


def test_simulate_long_stop_loss():
    result = simulate_execution(
        order_plan=sample_plan("LONG"),
        slippage_pct=0.0,
        entry_fee_usd=0.05,
        exit_fee_usd=0.05,
        price_path=[
            {"timestamp": 1, "high": 60050, "low": 59895, "close": 59895},
        ],
    )

    assert result.outcome == "stop_loss"
    assert result.target == 0
    assert result.pnl["net_pnl_usd"] == pytest.approx(-1.15)


def test_simulate_short_take_profit():
    result = simulate_execution(
        order_plan=sample_plan("SHORT"),
        slippage_pct=0.0,
        entry_fee_usd=0.05,
        exit_fee_usd=0.05,
        price_path=[
            {"timestamp": 1, "high": 60000, "low": 59790, "close": 59790},
        ],
    )

    assert result.outcome == "take_profit"
    assert result.target == 1
    assert result.pnl["net_pnl_usd"] == pytest.approx(2.00)


def test_simulate_time_barrier():
    result = simulate_execution(
        order_plan=sample_plan("LONG"),
        slippage_pct=0.0,
        entry_fee_usd=0.05,
        exit_fee_usd=0.05,
        price_path=[
            {"timestamp": 1, "high": 60050, "low": 59950, "close": 60025},
        ],
    )

    assert result.outcome == "time_barrier"
    assert result.target is None
    assert result.pnl["net_pnl_usd"] == pytest.approx(0.15)


def test_simulate_with_slippage_reduces_profit():
    no_slippage = simulate_execution(
        order_plan=sample_plan("LONG"),
        slippage_pct=0.0,
        entry_fee_usd=0.05,
        exit_fee_usd=0.05,
        price_path=[
            {"timestamp": 1, "high": 60210, "low": 60000, "close": 60210},
        ],
    )

    with_slippage = simulate_execution(
        order_plan=sample_plan("LONG"),
        slippage_pct=0.0005,
        entry_fee_usd=0.05,
        exit_fee_usd=0.05,
        price_path=[
            {"timestamp": 1, "high": 60300, "low": 60000, "close": 60300},
        ],
    )

    assert with_slippage.pnl["net_pnl_usd"] < no_slippage.pnl["net_pnl_usd"]


def test_simulate_with_funding_cost():
    result = simulate_execution(
        order_plan=sample_plan("LONG"),
        slippage_pct=0.0,
        entry_fee_usd=0.05,
        exit_fee_usd=0.05,
        funding_cost_usd=0.20,
        price_path=[
            {"timestamp": 1, "high": 60210, "low": 60000, "close": 60210},
        ],
    )

    assert result.pnl["net_pnl_usd"] == pytest.approx(1.80)