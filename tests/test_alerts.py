from dashboard.config import DashboardConfig
from observability.health import build_system_health
from ops.alerts import (
    AlertConfig,
    OperationalState,
    dispatch_console_alerts,
    evaluate_alerts,
    evaluate_dashboard_alerts,
    evaluate_operational_alerts,
    format_alert_for_console,
)


def sample_dashboard_summary():
    return {
        "paper_trading": {
            "metrics": {
                "fill_rate": 0.20,
                "average_slippage_error_pct": 0.002,
            }
        },
        "full_backtest": {
            "metrics": {
                "max_drawdown_pct": 0.25,
            }
        },
        "calibration": {
            "metrics": {
                "brier_score": 0.30,
                "expected_calibration_error": 0.20,
            }
        },
    }


def test_operational_alerts_kill_switch():
    config = AlertConfig()
    state = OperationalState(kill_switch_active=True)

    alerts = evaluate_operational_alerts(
        state=state,
        config=config,
    )

    assert any(alert.code == "KILL_SWITCH_ACTIVE" for alert in alerts)


def test_operational_alerts_model_ood():
    config = AlertConfig()
    state = OperationalState(model_ood=True)

    alerts = evaluate_operational_alerts(
        state=state,
        config=config,
    )

    assert any(alert.code == "MODEL_OOD" for alert in alerts)


def test_operational_alerts_api_errors():
    config = AlertConfig(max_api_errors=5)
    state = OperationalState(api_error_count=5)

    alerts = evaluate_operational_alerts(
        state=state,
        config=config,
    )

    assert any(alert.code == "API_REPEATED_ERRORS" for alert in alerts)


def test_operational_alerts_websocket_disconnect():
    config = AlertConfig(max_ws_disconnected_seconds=30)
    state = OperationalState(
        websocket_connected=False,
        ws_disconnected_seconds=45,
    )

    alerts = evaluate_operational_alerts(
        state=state,
        config=config,
    )

    assert any(alert.code == "WEBSOCKET_DISCONNECTED" for alert in alerts)


def test_dashboard_alerts_trigger_thresholds():
    config = AlertConfig()

    alerts = evaluate_dashboard_alerts(
        summary=sample_dashboard_summary(),
        config=config,
    )

    codes = {alert.code for alert in alerts}

    assert "LOW_FILL_RATE" in codes
    assert "HIGH_SLIPPAGE_ERROR" in codes
    assert "BACKTEST_DRAWDOWN_HIGH" in codes
    assert "BRIER_SCORE_HIGH" in codes
    assert "ECE_HIGH" in codes


def test_evaluate_alerts_combined(tmp_path):
    dashboard_config = DashboardConfig(
        paper_trading_dir=tmp_path,
        full_backtest_dir=tmp_path,
        model_evaluation_dir=tmp_path,
    )

    health = build_system_health(dashboard_config)

    result = evaluate_alerts(
        dashboard_summary=sample_dashboard_summary(),
        health=health,
        operational_state={"kill_switch_active": True},
        config=AlertConfig(),
        dashboard_config=dashboard_config,
    )

    assert result.ok is False
    assert result.alerts_count >= 1
    assert result.critical_count >= 1


def test_format_alert_for_console():
    result = evaluate_alerts(
        dashboard_summary=sample_dashboard_summary(),
        operational_state={"kill_switch_active": True},
        config=AlertConfig(),
        dashboard_config=DashboardConfig(),
    )

    line = format_alert_for_console(result.alerts[0])

    assert "[" in line
    assert "-" in line


def test_dispatch_console_alerts_ok(capsys):
    result = evaluate_alerts(
        dashboard_summary={},
        operational_state={},
        config=AlertConfig(),
        dashboard_config=DashboardConfig(),
    )

    lines = dispatch_console_alerts(result)
    captured = capsys.readouterr()

    assert lines
    assert captured.out