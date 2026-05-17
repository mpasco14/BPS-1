from risk.sizing import (
    calculate_edge_ratio,
    calculate_expected_value,
    calculate_fractional_kelly_position,
    calculate_kelly_fraction,
)


def test_calculate_expected_value():
    ev = calculate_expected_value(
        prob_win=0.6,
        profit_usd=2.10,
        loss_usd=1.05,
        fees_usd=0.10,
    )

    assert ev > 0


def test_calculate_edge_ratio():
    edge = calculate_edge_ratio(
        expected_value_usd=0.50,
        loss_usd=1.00,
    )

    assert edge == 0.5


def test_calculate_kelly_fraction():
    kelly = calculate_kelly_fraction(
        edge=0.10,
        odds=2.0,
    )

    assert kelly == 0.05


def test_fractional_kelly_position_caps_by_bankroll():
    plan = calculate_fractional_kelly_position(
        bankroll_usd=2000,
        edge=0.10,
        odds=2.0,
        market_liquidity_usd=100000,
        reduction_factor=0.10,
        max_bankroll_pct=0.005,
    )

    assert plan.is_tradeable is True
    assert plan.final_position_usd <= 10


def test_fractional_kelly_blocks_negative_edge():
    plan = calculate_fractional_kelly_position(
        bankroll_usd=2000,
        edge=-0.01,
        odds=2.0,
        market_liquidity_usd=100000,
    )

    assert plan.is_tradeable is False
    assert "non_positive_edge" in plan.blockers