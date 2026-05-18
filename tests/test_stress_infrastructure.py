from datetime import datetime, timedelta, timezone

from execution.binance_futures_client import BinanceFuturesConfig, BinanceFuturesRestClient
from execution.cancel_order import CancelPolicy, OpenOrderState, cancel_order_if_needed, evaluate_cancel_order
from execution.limit_order import rules_from_symbol_info
from execution.order_router import route_signal_to_order
from risk.exposure import get_exposure_store
from risk.kill_switch import evaluate_kill_switch
from risk.risk_manager import RiskProfile
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


def paper_client():
    return BinanceFuturesRestClient(
        config=BinanceFuturesConfig(execution_mode="paper")
    )


class Api429Client:
    def cancel_order(self, *args, **kwargs):
        raise RuntimeError("429 Too Many Requests")


def test_websocket_disconnect_blocks_order_router():
    result = route_signal_to_order(
        signal=sample_signal(),
        entry_price=60000,
        rules=symbol_rules(),
        client=paper_client(),
        profile=custom_profile(),
        kill_switch_input={"ws_disconnected_seconds": 31},
    )

    assert result.decision == "BLOCKED"
    assert result.record["status"] == "KILL_SWITCH_ACTIVE"


def test_redis_unavailable_degrades_to_memory_store(monkeypatch):
    monkeypatch.setenv("EXPOSURE_STORE_BACKEND", "memory")

    store = get_exposure_store()
    snapshot = store.load()

    assert snapshot.total_bankroll_usd > 0


def test_model_nan_or_ood_triggers_kill_switch():
    state = evaluate_kill_switch({"model_ood": True})

    assert state.active is True
    assert "model_out_of_distribution" in state.triggers
    assert state.cancel_open_orders is True


def test_api_429_triggers_kill_switch():
    state = evaluate_kill_switch({"api_error_count": 5})

    assert state.active is True
    assert "api_repeated_errors" in state.triggers


def test_api_429_during_cancel_is_handled_gracefully():
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
        client=Api429Client(),
    )

    assert result.attempted is True
    assert result.cancelled is False
    assert "429" in result.error