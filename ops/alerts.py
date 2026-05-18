"""
Alerting layer for BTC Binance Futures bot.

Responsabilidades:
- Avaliar métricas operacionais.
- Gerar eventos de alerta padronizados.
- Preparar integração futura com Telegram/Discord/Email/Alertmanager.
- Não executar ordens.
- Não alterar estado de trading.

Nesta primeira versão, o canal padrão é console.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from dashboard.config import DashboardConfig, load_dashboard_config
from dashboard.metrics_builder import build_dashboard_summary
from observability.health import SystemHealth, build_system_health


load_dotenv()


AlertSeverity = Literal["INFO", "WARNING", "CRITICAL"]
AlertChannel = Literal["console", "telegram", "discord", "email", "alertmanager"]


class AlertConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    service_name: str = "btc-binance-bot"
    channel: AlertChannel = "console"

    min_fill_rate: float = 0.60
    max_daily_drawdown_pct: float = 0.015
    max_backtest_drawdown_pct: float = 0.20
    max_slippage_error_pct: float = 0.001
    max_ece: float = 0.15
    max_brier_score: float = 0.25

    max_ws_disconnected_seconds: float = 30
    max_api_errors: int = 5

    trigger_on_kill_switch: bool = True
    trigger_on_model_ood: bool = True
    trigger_on_health_error: bool = True
    trigger_on_low_fill_rate: bool = True
    trigger_on_high_drawdown: bool = True
    trigger_on_high_slippage: bool = True
    trigger_on_bad_calibration: bool = True

    output_dir: Path = Path("artifacts/alerts")


class OperationalState(BaseModel):
    model_config = ConfigDict(extra="allow")

    kill_switch_active: bool = False
    daily_drawdown_pct: float = 0.0

    websocket_connected: bool = True
    ws_disconnected_seconds: float = 0.0

    model_ood: bool = False
    api_error_count: int = 0

    open_positions: int = 0
    btc_directional_exposure_pct: float = 0.0


class AlertEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    service: str
    severity: AlertSeverity
    code: str
    title: str
    message: str

    value: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AlertEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    service: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    ok: bool
    alerts_count: int
    critical_count: int
    warning_count: int

    alerts: list[dict[str, Any]] = Field(default_factory=list)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_alert_config() -> AlertConfig:
    channel = os.getenv("ALERTS_CHANNEL", "console").strip().lower()

    if channel not in {"console", "telegram", "discord", "email", "alertmanager"}:
        channel = "console"

    return AlertConfig(
        enabled=env_bool("ALERTS_ENABLED", True),
        service_name=os.getenv("ALERTS_SERVICE_NAME", "btc-binance-bot"),
        channel=channel,  # type: ignore[arg-type]
        min_fill_rate=env_float("ALERTS_MIN_FILL_RATE", 0.60),
        max_daily_drawdown_pct=env_float("ALERTS_MAX_DAILY_DRAWDOWN_PCT", 0.015),
        max_backtest_drawdown_pct=env_float("ALERTS_MAX_BACKTEST_DRAWDOWN_PCT", 0.20),
        max_slippage_error_pct=env_float("ALERTS_MAX_SLIPPAGE_ERROR_PCT", 0.001),
        max_ece=env_float("ALERTS_MAX_ECE", 0.15),
        max_brier_score=env_float("ALERTS_MAX_BRIER_SCORE", 0.25),
        max_ws_disconnected_seconds=env_float("ALERTS_MAX_WS_DISCONNECTED_SECONDS", 30),
        max_api_errors=env_int("ALERTS_MAX_API_ERRORS", 5),
        trigger_on_kill_switch=env_bool("ALERTS_TRIGGER_ON_KILL_SWITCH", True),
        trigger_on_model_ood=env_bool("ALERTS_TRIGGER_ON_MODEL_OOD", True),
        trigger_on_health_error=env_bool("ALERTS_TRIGGER_ON_HEALTH_ERROR", True),
        trigger_on_low_fill_rate=env_bool("ALERTS_TRIGGER_ON_LOW_FILL_RATE", True),
        trigger_on_high_drawdown=env_bool("ALERTS_TRIGGER_ON_HIGH_DRAWDOWN", True),
        trigger_on_high_slippage=env_bool("ALERTS_TRIGGER_ON_HIGH_SLIPPAGE", True),
        trigger_on_bad_calibration=env_bool("ALERTS_TRIGGER_ON_BAD_CALIBRATION", True),
        output_dir=Path(os.getenv("ALERTS_OUTPUT_DIR", "artifacts/alerts")),
    )


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def make_alert(
    *,
    config: AlertConfig,
    severity: AlertSeverity,
    code: str,
    title: str,
    message: str,
    value: float | int | str | bool | None = None,
    threshold: float | int | str | bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> AlertEvent:
    return AlertEvent(
        service=config.service_name,
        severity=severity,
        code=code,
        title=title,
        message=message,
        value=value,
        threshold=threshold,
        metadata=metadata or {},
    )


def evaluate_health_alerts(
    *,
    health: SystemHealth,
    config: AlertConfig,
) -> list[AlertEvent]:
    if not config.trigger_on_health_error:
        return []

    alerts: list[AlertEvent] = []

    if health.status != "ok":
        alerts.append(
            make_alert(
                config=config,
                severity="CRITICAL",
                code="HEALTH_STATUS_ERROR",
                title="System health error",
                message="O health check geral está em erro.",
                value=health.status,
                threshold="ok",
                metadata=health.model_dump(mode="json"),
            )
        )

    for check in health.checks:
        status = check.get("status")

        if status == "error":
            alerts.append(
                make_alert(
                    config=config,
                    severity="CRITICAL",
                    code="COMPONENT_HEALTH_ERROR",
                    title="Component health error",
                    message=f"Componente em erro: {check.get('name')}",
                    value=status,
                    threshold="ok",
                    metadata=check,
                )
            )

    return alerts


def evaluate_operational_alerts(
    *,
    state: OperationalState,
    config: AlertConfig,
) -> list[AlertEvent]:
    alerts: list[AlertEvent] = []

    if config.trigger_on_kill_switch and state.kill_switch_active:
        alerts.append(
            make_alert(
                config=config,
                severity="CRITICAL",
                code="KILL_SWITCH_ACTIVE",
                title="Kill switch ativo",
                message="O kill switch foi ativado. Novas entradas devem permanecer bloqueadas.",
                value=True,
                threshold=False,
            )
        )

    if (
        config.trigger_on_high_drawdown
        and state.daily_drawdown_pct >= config.max_daily_drawdown_pct
    ):
        alerts.append(
            make_alert(
                config=config,
                severity="CRITICAL",
                code="DAILY_DRAWDOWN_LIMIT",
                title="Drawdown diário acima do limite",
                message="O drawdown diário excedeu o limite configurado.",
                value=state.daily_drawdown_pct,
                threshold=config.max_daily_drawdown_pct,
            )
        )

    if (
        not state.websocket_connected
        or state.ws_disconnected_seconds > config.max_ws_disconnected_seconds
    ):
        alerts.append(
            make_alert(
                config=config,
                severity="CRITICAL",
                code="WEBSOCKET_DISCONNECTED",
                title="WebSocket desconectado",
                message="WebSocket desconectado por tempo acima do limite.",
                value=state.ws_disconnected_seconds,
                threshold=config.max_ws_disconnected_seconds,
            )
        )

    if config.trigger_on_model_ood and state.model_ood:
        alerts.append(
            make_alert(
                config=config,
                severity="CRITICAL",
                code="MODEL_OOD",
                title="Modelo em OOD",
                message="Modelo marcou input como fora da distribuição de treino.",
                value=True,
                threshold=False,
            )
        )

    if state.api_error_count >= config.max_api_errors:
        alerts.append(
            make_alert(
                config=config,
                severity="WARNING",
                code="API_REPEATED_ERRORS",
                title="Erros repetidos de API",
                message="Número de erros de API acima do limite.",
                value=state.api_error_count,
                threshold=config.max_api_errors,
            )
        )

    return alerts


def extract_dashboard_section(summary: dict[str, Any], section: str) -> dict[str, Any]:
    payload = summary.get(section)

    if isinstance(payload, dict):
        return payload

    return {}


def extract_metrics(section: dict[str, Any]) -> dict[str, Any]:
    metrics = section.get("metrics")

    if isinstance(metrics, dict):
        return metrics

    return {}


def evaluate_dashboard_alerts(
    *,
    summary: dict[str, Any],
    config: AlertConfig,
) -> list[AlertEvent]:
    alerts: list[AlertEvent] = []

    paper = extract_metrics(extract_dashboard_section(summary, "paper_trading"))
    backtest = extract_metrics(extract_dashboard_section(summary, "full_backtest"))
    calibration = extract_metrics(extract_dashboard_section(summary, "calibration"))

    fill_rate = safe_float(paper.get("fill_rate"))

    if (
        config.trigger_on_low_fill_rate
        and fill_rate is not None
        and fill_rate < config.min_fill_rate
    ):
        alerts.append(
            make_alert(
                config=config,
                severity="WARNING",
                code="LOW_FILL_RATE",
                title="Fill rate abaixo do esperado",
                message="A taxa de fills está abaixo do limite configurado.",
                value=fill_rate,
                threshold=config.min_fill_rate,
            )
        )

    slippage_error = safe_float(paper.get("average_slippage_error_pct"))

    if (
        config.trigger_on_high_slippage
        and slippage_error is not None
        and slippage_error > config.max_slippage_error_pct
    ):
        alerts.append(
            make_alert(
                config=config,
                severity="WARNING",
                code="HIGH_SLIPPAGE_ERROR",
                title="Slippage realizado acima do estimado",
                message="Diferença entre slippage realizado e estimado acima do limite.",
                value=slippage_error,
                threshold=config.max_slippage_error_pct,
            )
        )

    max_drawdown = safe_float(backtest.get("max_drawdown_pct"))

    if (
        config.trigger_on_high_drawdown
        and max_drawdown is not None
        and max_drawdown > config.max_backtest_drawdown_pct
    ):
        alerts.append(
            make_alert(
                config=config,
                severity="WARNING",
                code="BACKTEST_DRAWDOWN_HIGH",
                title="Max drawdown do backtest acima do limite",
                message="O max drawdown do backtest excedeu o limite configurado.",
                value=max_drawdown,
                threshold=config.max_backtest_drawdown_pct,
            )
        )

    brier = safe_float(calibration.get("brier_score"))

    if (
        config.trigger_on_bad_calibration
        and brier is not None
        and brier > config.max_brier_score
    ):
        alerts.append(
            make_alert(
                config=config,
                severity="WARNING",
                code="BRIER_SCORE_HIGH",
                title="Brier Score acima do limite",
                message="A calibração do modelo está pior que o limite configurado.",
                value=brier,
                threshold=config.max_brier_score,
            )
        )

    ece = safe_float(calibration.get("expected_calibration_error"))

    if (
        config.trigger_on_bad_calibration
        and ece is not None
        and ece > config.max_ece
    ):
        alerts.append(
            make_alert(
                config=config,
                severity="WARNING",
                code="ECE_HIGH",
                title="Expected Calibration Error acima do limite",
                message="ECE acima do limite configurado. Recalibração pode ser necessária.",
                value=ece,
                threshold=config.max_ece,
            )
        )

    return alerts


def evaluate_alerts(
    *,
    dashboard_summary: dict[str, Any] | None = None,
    health: SystemHealth | None = None,
    operational_state: OperationalState | dict[str, Any] | None = None,
    config: AlertConfig | None = None,
    dashboard_config: DashboardConfig | None = None,
) -> AlertEvaluationResult:
    resolved_config = config or load_alert_config()

    if not resolved_config.enabled:
        return AlertEvaluationResult(
            service=resolved_config.service_name,
            ok=True,
            alerts_count=0,
            critical_count=0,
            warning_count=0,
            alerts=[],
        )

    resolved_dashboard_config = dashboard_config or load_dashboard_config()

    resolved_summary = dashboard_summary
    if resolved_summary is None:
        resolved_summary = build_dashboard_summary(resolved_dashboard_config).model_dump(mode="json")

    resolved_health = health or build_system_health(resolved_dashboard_config)

    if operational_state is None:
        state = OperationalState()
    elif isinstance(operational_state, OperationalState):
        state = operational_state
    else:
        state = OperationalState.model_validate(operational_state)

    alerts: list[AlertEvent] = []
    alerts.extend(evaluate_health_alerts(health=resolved_health, config=resolved_config))
    alerts.extend(evaluate_operational_alerts(state=state, config=resolved_config))
    alerts.extend(evaluate_dashboard_alerts(summary=resolved_summary, config=resolved_config))

    critical_count = sum(1 for alert in alerts if alert.severity == "CRITICAL")
    warning_count = sum(1 for alert in alerts if alert.severity == "WARNING")

    return AlertEvaluationResult(
        service=resolved_config.service_name,
        ok=len(alerts) == 0,
        alerts_count=len(alerts),
        critical_count=critical_count,
        warning_count=warning_count,
        alerts=[alert.model_dump(mode="json") for alert in alerts],
    )


def format_alert_for_console(alert: dict[str, Any]) -> str:
    return (
        f"[{alert.get('severity')}] "
        f"{alert.get('code')} - "
        f"{alert.get('title')}: "
        f"{alert.get('message')} "
        f"(value={alert.get('value')}, threshold={alert.get('threshold')})"
    )


def dispatch_console_alerts(result: AlertEvaluationResult) -> list[str]:
    lines: list[str] = []

    for alert in result.alerts:
        line = format_alert_for_console(alert)
        print(line)
        lines.append(line)

    if not lines:
        line = "[OK] No alerts triggered"
        print(line)
        lines.append(line)

    return lines


def export_alert_evaluation(
    result: AlertEvaluationResult,
    *,
    output_dir: str | Path | None = None,
    name: str = "alerts_latest",
) -> Path:
    resolved_config = load_alert_config()
    resolved_output_dir = Path(output_dir or resolved_config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path