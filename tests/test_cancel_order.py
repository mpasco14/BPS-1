from datetime import datetime, timedelta, timezone

from execution.binance_futures_client import BinanceFuturesConfig, BinanceFuturesRestClient
from execution.cancel_order import (
    CancelPolicy,
    OpenOrderState,
    cancel_order_if_needed,
    evaluate_cancel_order,
)
from risk.kill_switch import evaluate_kill_switch


def sample_order(**overrides):
    data = {
        "symbol": "BTCUSDT",
        "client_order_id": "client-1",
        "order_id": 123,
        "side": "BUY",
        "price": 60000,
        "quantity": 0.01,
        "created_at": datetime.now(timezone.utc),
        "edge_valid": True,
        "spread_pct": 0.0001,
    }

    data.update(overrides)

    return OpenOrderState(**data)


def test_no_cancel_normal_order():
    decision = evaluate_cancel_order(
        sample_order(),
        policy=CancelPolicy(max_order_age_seconds=60),
    )

    assert decision.should_cancel is False
    assert decision.reasons == []


def test_cancel_when_edge_lost():
    decision = evaluate_cancel_order(
        sample_order(edge_valid=False),
        policy=CancelPolicy(),
    )

    assert decision.should_cancel is True
    assert "edge_lost" in decision.reasons


def test_cancel_when_spread_above_limit():
    decision = evaluate_cancel_order(
        sample_order(spread_pct=0.01),
        policy=CancelPolicy(max_spread_pct=0.002),
    )

    assert decision.should_cancel is True
    assert "spread_above_limit" in decision.reasons


def test_cancel_when_order_too_old():
    old_time = datetime.now(timezone.utc) - timedelta(seconds=120)

    decision = evaluate_cancel_order(
        sample_order(created_at=old_time),
        policy=CancelPolicy(max_order_age_seconds=60),
    )

    assert decision.should_cancel is True
    assert "order_too_old" in decision.reasons


def test_cancel_when_kill_switch_active():
    kill_state = evaluate_kill_switch({"model_ood": True})

    decision = evaluate_cancel_order(
        sample_order(),
        kill_switch_state=kill_state,
        policy=CancelPolicy(),
    )

    assert decision.should_cancel is True
    assert "kill_switch_active" in decision.reasons


def test_cancel_order_if_needed_paper():
    config = BinanceFuturesConfig(execution_mode="paper")
    client = BinanceFuturesRestClient(config=config)

    decision = evaluate_cancel_order(
        sample_order(edge_valid=False),
        policy=CancelPolicy(),
    )

    result = cancel_order_if_needed(
        order=sample_order(edge_valid=False),
        decision=decision,
        client=client,
    )

    assert result.attempted is True
    assert result.cancelled is True
    assert result.response["status"] == "CANCELED"