from strategy.orderbook import (
    OrderBookLevel,
    analyze_orderbook,
    calculate_book_imbalance,
    calculate_depth,
    calculate_liquidity_gap_pct,
    calculate_mid_price,
    calculate_spread,
    calculate_spread_pct,
    calculate_weighted_mid_price,
    extract_binance_levels,
    parse_orderbook_levels,
)


def sample_raw_orderbook():
    return {
        "symbol": "BTCUSDT",
        "bids": [
            ["59999.0", "2.0"],
            ["59998.0", "1.5"],
            ["59997.0", "1.0"],
            ["59996.0", "1.0"],
            ["59995.0", "1.0"],
        ],
        "asks": [
            ["60001.0", "1.0"],
            ["60002.0", "1.5"],
            ["60003.0", "1.0"],
            ["60004.0", "1.0"],
            ["60005.0", "1.0"],
        ],
    }


def test_parse_orderbook_levels_from_lists():
    levels = parse_orderbook_levels(
        [["60000", "1.5"], ["59999", "2.0"], ["0", "10"]],
        side="bid",
    )

    assert len(levels) == 2
    assert levels[0].price == 60000.0
    assert levels[0].quantity == 1.5


def test_parse_orderbook_levels_from_dicts():
    levels = parse_orderbook_levels(
        [
            {"price": "60001", "quantity": "1.0"},
            {"price": "60002", "qty": "2.0"},
            {"price": "60003", "size": "3.0"},
        ],
        side="ask",
    )

    assert len(levels) == 3
    assert levels[0].price == 60001.0
    assert levels[2].quantity == 3.0


def test_extract_binance_levels():
    bids, asks = extract_binance_levels(sample_raw_orderbook())

    assert len(bids) == 5
    assert len(asks) == 5
    assert bids[0].price == 59999.0
    assert asks[0].price == 60001.0


def test_calculate_depth():
    levels = [
        OrderBookLevel(price=60000, quantity=1),
        OrderBookLevel(price=59999, quantity=2),
    ]

    depth = calculate_depth(levels, top_n=2)

    assert depth.quantity == 3
    assert depth.notional == 179998


def test_mid_spread_and_spread_pct():
    spread = calculate_spread(59999, 60001)
    mid = calculate_mid_price(59999, 60001)
    spread_pct = calculate_spread_pct(spread=spread, mid_price=mid)

    assert spread == 2
    assert mid == 60000
    assert round(spread_pct, 6) == round(2 / 60000, 6)


def test_weighted_mid_price_reflects_bid_pressure():
    weighted_mid = calculate_weighted_mid_price(
        best_bid=59999,
        best_ask=60001,
        best_bid_qty=3,
        best_ask_qty=1,
    )

    assert weighted_mid is not None
    assert weighted_mid > 60000


def test_book_imbalance_positive_when_bid_depth_larger():
    imbalance = calculate_book_imbalance(
        bid_notional=200000,
        ask_notional=100000,
    )

    assert imbalance is not None
    assert imbalance > 0


def test_liquidity_gap_pct():
    asks = [
        OrderBookLevel(price=60001, quantity=1),
        OrderBookLevel(price=60002, quantity=1),
        OrderBookLevel(price=60010, quantity=1),
    ]

    gap = calculate_liquidity_gap_pct(asks, side="ask", top_n=3)

    assert gap > 0


def test_analyze_orderbook_tradeable():
    analysis = analyze_orderbook(
        raw=sample_raw_orderbook(),
        depth_levels=5,
        min_depth_usd=50000,
        max_spread_pct=0.002,
        max_liquidity_gap_pct=0.001,
    )

    assert analysis.symbol == "BTCUSDT"
    assert analysis.best_bid == 59999.0
    assert analysis.best_ask == 60001.0
    assert analysis.spread == 2.0
    assert analysis.spread_pct is not None
    assert analysis.bid_depth_notional > 0
    assert analysis.ask_depth_notional > 0
    assert -1 <= analysis.microstructure_score <= 1
    assert analysis.is_tradeable is True
    assert analysis.blockers == []


def test_analyze_orderbook_blocks_wide_spread():
    raw = {
        "symbol": "BTCUSDT",
        "bids": [["59900", "2"]],
        "asks": [["60100", "2"]],
    }

    analysis = analyze_orderbook(
        raw=raw,
        depth_levels=1,
        min_depth_usd=1000,
        max_spread_pct=0.001,
        max_liquidity_gap_pct=0.01,
    )

    assert analysis.is_tradeable is False
    assert "spread_too_wide" in analysis.blockers


def test_analyze_orderbook_blocks_insufficient_depth():
    raw = {
        "symbol": "BTCUSDT",
        "bids": [["59999", "0.001"]],
        "asks": [["60001", "0.001"]],
    }

    analysis = analyze_orderbook(
        raw=raw,
        depth_levels=1,
        min_depth_usd=1000,
        max_spread_pct=0.002,
        max_liquidity_gap_pct=0.01,
    )

    assert analysis.is_tradeable is False
    assert "insufficient_depth" in analysis.blockers


def test_analyze_orderbook_supports_ws_keys_b_and_a():
    raw = {
        "s": "BTCUSDT",
        "b": [["59999", "2"]],
        "a": [["60001", "1"]],
    }

    analysis = analyze_orderbook(
        raw=raw,
        depth_levels=1,
        min_depth_usd=1000,
        max_spread_pct=0.002,
        max_liquidity_gap_pct=0.01,
    )

    assert analysis.symbol == "BTCUSDT"
    assert analysis.best_bid == 59999.0
    assert analysis.best_ask == 60001.0