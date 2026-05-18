from argparse import Namespace

from scripts.run_alerts_check import build_operational_state_from_args


def test_build_operational_state_from_args_default():
    args = Namespace(
        kill_switch_active=False,
        daily_drawdown_pct=0.0,
        websocket_connected=True,
        ws_disconnected_seconds=0.0,
        model_ood=False,
        api_error_count=0,
        open_positions=0,
        btc_directional_exposure_pct=0.0,
    )

    state = build_operational_state_from_args(args)

    assert state.kill_switch_active is False
    assert state.websocket_connected is True


def test_build_operational_state_marks_ws_disconnected():
    args = Namespace(
        kill_switch_active=False,
        daily_drawdown_pct=0.0,
        websocket_connected=True,
        ws_disconnected_seconds=45.0,
        model_ood=False,
        api_error_count=0,
        open_positions=0,
        btc_directional_exposure_pct=0.0,
    )

    state = build_operational_state_from_args(args)

    assert state.websocket_connected is False
    assert state.ws_disconnected_seconds == 45.0