import pytest

from execution.limit_order import (
    build_limit_order_from_plan,
    limit_order_to_params,
    round_price_for_side,
    round_quantity,
    rules_from_symbol_info,
)
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
        max_daily_loss_usd=60,
        max_trade_loss_usd=2,
        max_consecutive_losses=3,
        max_open_positions=5,
        max_open_orders=5,
        max_spread_pct=0.002,
        min_liquidity_usd=50000,
        min_confidence=0.65,
    )


def sample_symbol_info():
    return {
        "symbol": "BTCUSDT",
        "filters": [
            {
                "filterType": "PRICE_FILTER",
                "tickSize": "0.10",
            },
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.001",
                "stepSize": "0.001",
            },
            {
                "filterType": "MIN_NOTIONAL",
                "notional": "5",
            },
        ],
    }


def test_rules_from_symbol_info():
    rules = rules_from_symbol_info(sample_symbol_info())

    assert rules.symbol == "BTCUSDT"
    assert rules.tick_size == 0.10
    assert rules.step_size == 0.001
    assert rules.min_notional == 5


def test_round_quantity():
    assert round_quantity(0.0109, 0.001) == pytest.approx(0.010)


def test_round_price_for_side():
    assert round_price_for_side(60000.09, 0.10, "BUY") == pytest.approx(60000.0)
    assert round_price_for_side(60000.01, 0.10, "SELL") == pytest.approx(60000.1)


def test_build_long_limit_order_from_plan():
    plan = calculate_order_plan(
        direction="LONG",
        entry_price=60000,
        timeframe="5m",
        profile=custom_profile(),
    )

    rules = rules_from_symbol_info(sample_symbol_info())

    payload = build_limit_order_from_plan(
        plan=plan,
        rules=rules,
        slippage_pct=0.001,
    )

    assert payload.symbol == "BTCUSDT"
    assert payload.side == "BUY"
    assert payload.type == "LIMIT"
    assert payload.timeInForce == "GTC"
    assert payload.quantity == "0.010"
    assert payload.price == "60060.00"

    params = limit_order_to_params(payload)

    assert params["symbol"] == "BTCUSDT"
    assert params["side"] == "BUY"
    assert "metadata" not in params


def test_build_short_limit_order_from_plan():
    plan = calculate_order_plan(
        direction="SHORT",
        entry_price=60000,
        timeframe="5m",
        profile=custom_profile(),
    )

    rules = rules_from_symbol_info(sample_symbol_info())

    payload = build_limit_order_from_plan(
        plan=plan,
        rules=rules,
        slippage_pct=0.001,
    )

    assert payload.side == "SELL"
    assert payload.quantity == "0.010"
    assert payload.price == "59940.00"