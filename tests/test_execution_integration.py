from datetime import datetime, timedelta, timezone

from execution.binance_futures_client import BinanceFuturesConfig, BinanceFuturesRestClient
from execution.cancel_order import CancelPolicy, OpenOrderState, cancel_order_if_needed, evaluate_cancel_order
from execution.fill_monitor import (
    apply_fill_update_to_exposure,
    decide_partial_fill_action,
    normalize_order_trade_update,
)
from execution.limit_order import build_limit_order_from_plan, rules_from_symbol_info
from execution.order_router import route_signal_to_order
from risk.exposure import ExposureSnapshot, default_exposure_snapshot
from risk.risk_manager import RiskProfile, calculate_order_plan
from strategy.signal_engine import generate_signal


def fixed_now():
    return datetime(2026, 5, 15, 18, 1, 0, tzinfo=timezone.utc)


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


def symbol_rules():
    return rules_from_symbol_info(
        {
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ],
        }
    )


def paper_client():
    return BinanceFuturesRestClient(
        config=BinanceFuturesConfig(execution_mode="paper")
    )


def exposure():
    return ExposureSnapshot(
        total_bankroll_usd=2000,
        daily_pnl_usd=0,
        open_positions=0,
        exposure_per_market={},
        exposure_by_timeframe={},
        btc_directional_exposure_usd=0,
    )


def sample_signal():
    features = {
        "timestamp": "2026-05-15T18:00:00+00:00",
        "venue": "binance_futures",
        "instrument_id": "BTCUSDT",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "tech_score": 0.9,
        "microstructure_score": 0.4,
        "onchain_score": 0.05,
        "sentiment_score": 0.03,
        "combined_score": 0.9,
        "binance_spread_pct": 0.0001,
        "binance_liquidity_usd": 100000,
        "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
    }

    signal = generate_signal(features, now=fixed_now())

    return signal.model_copy(
        update={
            "edge": 0.50 / 1.05,
            "prediction": {"expected_value_usd": 0.50},
        }
    )


def sample_fill_event(status="PARTIALLY_FILLED", cumulative="0.006", last="0.006"):
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


def test_limit_order_creation_matches_binance_rules():
    plan = calculate_order_plan(
        direction="LONG",
        entry_price=60000,
        timeframe="5m",
        profile=custom_profile(),
    )

    payload = build_limit_order_from_plan(
        plan=plan,
        rules=symbol_rules(),
        slippage_pct=0.001,
    )

    assert payload.symbol == "BTCUSDT"
    assert payload.side == "BUY"
    assert payload.quantity == "0.010"
    assert payload.price == "60060.00"


def test_order_router_uses_paper_client_and_blocks_live_execution():
    result = route_signal_to_order(
        signal=sample_signal(),
        entry_price=60000,
        rules=symbol_rules(),
        client=paper_client(),
        profile=custom_profile(),
        exposure_snapshot=exposure(),
        market_liquidity_usd=100000,
    )

    assert result.decision == "ROUTED"
    assert result.record["exchange_response"]["paper"] is True
    assert result.record["order_payload"]["symbol"] == "BTCUSDT"


def test_partial_fill_updates_exposure_and_keeps_rest_when_edge_valid():
    update = normalize_order_trade_update(sample_fill_event())
    decision = decide_partial_fill_action(update, edge_valid=True)

    snapshot = default_exposure_snapshot()
    updated = apply_fill_update_to_exposure(
        snapshot,
        update,
        timeframe="5m",
        leverage=30,
    )

    assert decision.action == "KEEP_REST"
    assert updated.open_positions == 1
    assert updated.exposure_per_market["BTCUSDT"] > 0


def test_partial_fill_cancels_rest_when_edge_disappears():
    update = normalize_order_trade_update(sample_fill_event())
    decision = decide_partial_fill_action(update, edge_valid=False)

    assert decision.action == "CANCEL_REST"


def test_order_timeout_cancels_order_in_paper_mode():
    old_time = datetime.now(timezone.utc) - timedelta(seconds=120)

    order = OpenOrderState(
        symbol="BTCUSDT",
        client_order_id="client-1",
        order_id=123,
        side="BUY",
        price=60000,
        quantity=0.01,
        created_at=old_time,
        edge_valid=True,
        spread_pct=0.0001,
    )

    decision = evaluate_cancel_order(
        order,
        policy=CancelPolicy(max_order_age_seconds=60),
    )

    result = cancel_order_if_needed(
        order=order,
        decision=decision,
        client=paper_client(),
    )

    assert decision.should_cancel is True
    assert "order_too_old" in decision.reasons
    assert result.cancelled is True