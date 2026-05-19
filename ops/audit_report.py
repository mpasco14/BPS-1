"""
Weekly audit report.

Responsabilidades:
- Consolidar relatórios recentes.
- Auditar paper trading, full backtest, calibração, alertas e ops.
- Gerar recomendações operacionais.
- Exportar relatório semanal.

Este módulo NÃO executa ordens.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


AuditStatus = Literal["PASS", "WARN", "FAIL"]


class WeeklyAuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_dir: Path = Path("artifacts/ops")

    min_fill_rate: float = 0.60
    min_profit_factor: float = 1.10
    max_drawdown_pct: float = 0.20
    max_ece: float = 0.15
    max_brier_score: float = 0.25


class AuditItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: AuditStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    recommendation: str | None = None


class WeeklyAuditReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "weekly_audit"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: str
    passed: bool

    items_count: int
    pass_count: int
    warn_count: int
    fail_count: int

    items: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    source_files: dict[str, str | None] = Field(default_factory=dict)


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


def load_weekly_audit_config() -> WeeklyAuditConfig:
    return WeeklyAuditConfig(
        enabled=env_bool("WEEKLY_AUDIT_ENABLED", True),
        output_dir=Path(os.getenv("WEEKLY_AUDIT_OUTPUT_DIR", "artifacts/ops")),
        min_fill_rate=env_float("WEEKLY_AUDIT_MIN_FILL_RATE", 0.60),
        min_profit_factor=env_float("WEEKLY_AUDIT_MIN_PROFIT_FACTOR", 1.10),
        max_drawdown_pct=env_float("WEEKLY_AUDIT_MAX_DRAWDOWN_PCT", 0.20),
        max_ece=env_float("WEEKLY_AUDIT_MAX_ECE", 0.15),
        max_brier_score=env_float("WEEKLY_AUDIT_MAX_BRIER_SCORE", 0.25),
    )


def make_item(
    *,
    code: str,
    status: AuditStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    recommendation: str | None = None,
) -> AuditItem:
    return AuditItem(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        recommendation=recommendation,
    )


def latest_file(directory: str | Path, pattern: str) -> Path | None:
    path = Path(directory)

    if not path.exists():
        return None

    files = [item for item in path.glob(pattern) if item.is_file()]

    if not files:
        return None

    return max(files, key=lambda item: item.stat().st_mtime)


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def audit_paper_trading(
    *,
    report: dict[str, Any] | None,
    config: WeeklyAuditConfig,
) -> list[AuditItem]:
    if not report:
        return [
            make_item(
                code="PAPER_REPORT_MISSING",
                status="WARN",
                title="Paper trading ausente",
                message="Nenhum relatório de paper trading foi encontrado.",
                recommendation="Rodar paper trading contínuo antes de testnet/live.",
            )
        ]

    metrics = report.get("metrics") or {}
    fill_rate = safe_float(metrics.get("fill_rate"))
    net_pnl = safe_float(metrics.get("net_pnl_usd"))
    win_rate = safe_float(metrics.get("win_rate"))

    items: list[AuditItem] = []

    if fill_rate is not None and fill_rate >= config.min_fill_rate:
        items.append(
            make_item(
                code="PAPER_FILL_RATE_OK",
                status="PASS",
                title="Paper fill rate OK",
                message="Fill rate de paper trading dentro do esperado.",
                value=fill_rate,
                expected=f">={config.min_fill_rate}",
            )
        )
    else:
        items.append(
            make_item(
                code="PAPER_FILL_RATE_LOW",
                status="WARN",
                title="Paper fill rate baixo",
                message="Fill rate de paper trading abaixo do esperado ou ausente.",
                value=fill_rate,
                expected=f">={config.min_fill_rate}",
                recommendation="Verificar slippage, liquidez, spread e regras de roteamento.",
            )
        )

    if net_pnl is not None and net_pnl > 0:
        items.append(
            make_item(
                code="PAPER_PNL_POSITIVE",
                status="PASS",
                title="Paper PnL positivo",
                message="Paper trading gerou PnL líquido positivo.",
                value=net_pnl,
                expected=">0",
            )
        )
    else:
        items.append(
            make_item(
                code="PAPER_PNL_NOT_POSITIVE",
                status="WARN",
                title="Paper PnL não positivo",
                message="Paper trading não gerou PnL positivo ou métrica está ausente.",
                value=net_pnl,
                expected=">0",
                recommendation="Não avançar para live sem validar edge em paper/testnet.",
            )
        )

    if win_rate is not None:
        items.append(
            make_item(
                code="PAPER_WIN_RATE_RECORDED",
                status="PASS",
                title="Win rate registrado",
                message="Win rate disponível para auditoria.",
                value=win_rate,
            )
        )

    return items


def audit_backtest(
    *,
    report: dict[str, Any] | None,
    config: WeeklyAuditConfig,
) -> list[AuditItem]:
    if not report:
        return [
            make_item(
                code="BACKTEST_REPORT_MISSING",
                status="WARN",
                title="Backtest ausente",
                message="Nenhum relatório de full backtest foi encontrado.",
                recommendation="Rodar full backtest com custos antes de qualquer promoção de modelo.",
            )
        ]

    metrics = report.get("metrics") or {}
    profit_factor = safe_float(metrics.get("profit_factor"))
    max_drawdown = safe_float(metrics.get("max_drawdown_pct"))
    net_pnl = safe_float(metrics.get("net_pnl_usd"))

    items: list[AuditItem] = []

    if profit_factor is not None and profit_factor >= config.min_profit_factor:
        items.append(
            make_item(
                code="BACKTEST_PROFIT_FACTOR_OK",
                status="PASS",
                title="Profit factor OK",
                message="Profit factor acima do mínimo.",
                value=profit_factor,
                expected=f">={config.min_profit_factor}",
            )
        )
    else:
        items.append(
            make_item(
                code="BACKTEST_PROFIT_FACTOR_LOW",
                status="WARN",
                title="Profit factor baixo",
                message="Profit factor abaixo do mínimo ou ausente.",
                value=profit_factor,
                expected=f">={config.min_profit_factor}",
                recommendation="Revisar thresholds de entrada e custos de execução.",
            )
        )

    if max_drawdown is not None and max_drawdown <= config.max_drawdown_pct:
        items.append(
            make_item(
                code="BACKTEST_DRAWDOWN_OK",
                status="PASS",
                title="Drawdown OK",
                message="Max drawdown dentro do limite.",
                value=max_drawdown,
                expected=f"<={config.max_drawdown_pct}",
            )
        )
    else:
        items.append(
            make_item(
                code="BACKTEST_DRAWDOWN_HIGH",
                status="WARN",
                title="Drawdown alto",
                message="Max drawdown acima do limite ou ausente.",
                value=max_drawdown,
                expected=f"<={config.max_drawdown_pct}",
                recommendation="Reduzir sizing, alavancagem efetiva ou frequência de entradas.",
            )
        )

    if net_pnl is not None and net_pnl > 0:
        items.append(
            make_item(
                code="BACKTEST_PNL_POSITIVE",
                status="PASS",
                title="Backtest PnL positivo",
                message="Backtest possui PnL líquido positivo.",
                value=net_pnl,
                expected=">0",
            )
        )
    else:
        items.append(
            make_item(
                code="BACKTEST_PNL_NOT_POSITIVE",
                status="WARN",
                title="Backtest PnL não positivo",
                message="Backtest não possui PnL positivo ou métrica está ausente.",
                value=net_pnl,
                expected=">0",
                recommendation="Não promover modelo sem backtest positivo com custos.",
            )
        )

    return items


def audit_calibration(
    *,
    report: dict[str, Any] | None,
    config: WeeklyAuditConfig,
) -> list[AuditItem]:
    if not report:
        return [
            make_item(
                code="CALIBRATION_REPORT_MISSING",
                status="WARN",
                title="Calibração ausente",
                message="Nenhum relatório de calibração foi encontrado.",
                recommendation="Rodar avaliação de calibração antes de usar edge do modelo.",
            )
        ]

    brier = safe_float(report.get("brier_score"))
    ece = safe_float(report.get("expected_calibration_error"))

    items: list[AuditItem] = []

    if brier is not None and brier <= config.max_brier_score:
        items.append(
            make_item(
                code="CALIBRATION_BRIER_OK",
                status="PASS",
                title="Brier Score OK",
                message="Brier Score dentro do limite.",
                value=brier,
                expected=f"<={config.max_brier_score}",
            )
        )
    else:
        items.append(
            make_item(
                code="CALIBRATION_BRIER_HIGH",
                status="WARN",
                title="Brier Score alto",
                message="Brier Score acima do limite ou ausente.",
                value=brier,
                expected=f"<={config.max_brier_score}",
                recommendation="Recalibrar probabilidades ou revisar treinamento.",
            )
        )

    if ece is not None and ece <= config.max_ece:
        items.append(
            make_item(
                code="CALIBRATION_ECE_OK",
                status="PASS",
                title="ECE OK",
                message="Expected Calibration Error dentro do limite.",
                value=ece,
                expected=f"<={config.max_ece}",
            )
        )
    else:
        items.append(
            make_item(
                code="CALIBRATION_ECE_HIGH",
                status="WARN",
                title="ECE alto",
                message="Expected Calibration Error acima do limite ou ausente.",
                value=ece,
                expected=f"<={config.max_ece}",
                recommendation="Recalibrar com Platt/Isotonic antes de confiar em EV.",
            )
        )

    return items


def audit_alerts(
    *,
    report: dict[str, Any] | None,
) -> list[AuditItem]:
    if not report:
        return [
            make_item(
                code="ALERT_REPORT_MISSING",
                status="WARN",
                title="Relatório de alertas ausente",
                message="Nenhum relatório de alertas foi encontrado.",
                recommendation="Executar run_alerts_check.py com export semanalmente.",
            )
        ]

    critical_count = int(report.get("critical_count", 0) or 0)
    warning_count = int(report.get("warning_count", 0) or 0)

    if critical_count > 0:
        return [
            make_item(
                code="ALERTS_CRITICAL_PRESENT",
                status="FAIL",
                title="Alertas críticos presentes",
                message="Existem alertas críticos que precisam ser resolvidos.",
                value={"critical_count": critical_count, "warning_count": warning_count},
                expected={"critical_count": 0},
                recommendation="Resolver alertas críticos antes de qualquer operação.",
            )
        ]

    if warning_count > 0:
        return [
            make_item(
                code="ALERTS_WARNINGS_PRESENT",
                status="WARN",
                title="Alertas de warning presentes",
                message="Existem alertas de warning para revisão.",
                value={"critical_count": critical_count, "warning_count": warning_count},
                expected={"warning_count": 0},
                recommendation="Revisar warnings e decidir se bloqueiam avanço operacional.",
            )
        ]

    return [
        make_item(
            code="ALERTS_CLEAR",
            status="PASS",
            title="Sem alertas ativos",
            message="Nenhum alerta crítico ou warning encontrado.",
            value={"critical_count": critical_count, "warning_count": warning_count},
        )
    ]


def collect_recommendations(items: list[AuditItem]) -> list[str]:
    recommendations: list[str] = []

    for item in items:
        if item.recommendation and item.recommendation not in recommendations:
            recommendations.append(item.recommendation)

    return recommendations


def build_weekly_audit_report(
    *,
    config: WeeklyAuditConfig | None = None,
) -> WeeklyAuditReport:
    resolved_config = config or load_weekly_audit_config()

    if not resolved_config.enabled:
        item = make_item(
            code="WEEKLY_AUDIT_DISABLED",
            status="FAIL",
            title="Weekly audit disabled",
            message="WEEKLY_AUDIT_ENABLED está falso.",
            recommendation="Habilitar auditoria semanal para operação contínua.",
        )

        return WeeklyAuditReport(
            status="FAIL",
            passed=False,
            items_count=1,
            pass_count=0,
            warn_count=0,
            fail_count=1,
            items=[item.model_dump(mode="json")],
            recommendations=[item.recommendation] if item.recommendation else [],
        )

    paper_path = latest_file("artifacts/paper_trading", "*_summary.json")
    backtest_path = latest_file("artifacts/full_backtest", "*_summary.json")
    calibration_path = latest_file("artifacts/model_evaluation", "*.json")
    alerts_path = latest_file("artifacts/alerts", "*.json")

    items: list[AuditItem] = []
    items.extend(audit_paper_trading(report=load_json(paper_path), config=resolved_config))
    items.extend(audit_backtest(report=load_json(backtest_path), config=resolved_config))
    items.extend(audit_calibration(report=load_json(calibration_path), config=resolved_config))
    items.extend(audit_alerts(report=load_json(alerts_path)))

    pass_count = sum(1 for item in items if item.status == "PASS")
    warn_count = sum(1 for item in items if item.status == "WARN")
    fail_count = sum(1 for item in items if item.status == "FAIL")

    passed = fail_count == 0

    return WeeklyAuditReport(
        status="PASS" if passed else "FAIL",
        passed=passed,
        items_count=len(items),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        items=[item.model_dump(mode="json") for item in items],
        recommendations=collect_recommendations(items),
        source_files={
            "paper_trading": str(paper_path) if paper_path else None,
            "full_backtest": str(backtest_path) if backtest_path else None,
            "calibration": str(calibration_path) if calibration_path else None,
            "alerts": str(alerts_path) if alerts_path else None,
        },
    )


def export_weekly_audit_report(
    report: WeeklyAuditReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "weekly_audit_latest",
) -> Path:
    config = load_weekly_audit_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path