from risk.kill_switch import evaluate_kill_switch, should_cancel_open_orders


def test_kill_switch_inactive_on_normal_conditions():
    state = evaluate_kill_switch(
        {
            "ws_disconnected_seconds": 0,
            "btc_price_divergence_pct": 0,
            "spread_pct": 0.0001,
            "slippage_pct": 0.0001,
            "daily_drawdown_pct": 0,
            "model_ood": False,
            "api_error_count": 0,
        }
    )

    assert state.active is False
    assert should_cancel_open_orders(state) is False


def test_kill_switch_triggers_on_websocket_disconnect():
    state = evaluate_kill_switch(
        {
            "ws_disconnected_seconds": 31,
        }
    )

    assert state.active is True
    assert "websocket_disconnected_too_long" in state.triggers
    assert should_cancel_open_orders(state) is True


def test_kill_switch_triggers_on_model_ood():
    state = evaluate_kill_switch(
        {
            "model_ood": True,
        }
    )

    assert state.active is True
    assert "model_out_of_distribution" in state.triggers


def test_kill_switch_triggers_on_api_errors():
    state = evaluate_kill_switch(
        {
            "api_error_count": 5,
        }
    )

    assert state.active is True
    assert "api_repeated_errors" in state.triggers