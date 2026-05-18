"""
Compliance checks for Binance Futures bot.

Responsabilidades:
- Verificar pré-requisitos operacionais antes de testnet/live.
- Bloquear live trading por padrão.
- Gerar relatório auditável.
- Não executar ordens.
- Não alterar estado do sistema.

Este módulo NÃO substitui parecer jurídico formal.
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


CheckStatus = Literal["PASS", "WARN", "FAIL"]


class ComplianceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_dir: Path = Path("artifacts/ops")

    operator_country: str = "BR"

    require_legal_review_before_live: bool = True
    legal_review_approved: bool = False

    require_paper_trading: bool = True
    require_backtest_positive: bool = True
    require_calibration_valid: bool = True
    require_kill_switch_tested: bool = True
    require_alerts_enabled: bool = True
    require_observability_enabled: bool = True

    require_live_trading_disabled_by_default: bool = True


class ComplianceCheckItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: CheckStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class ComplianceReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "compliance_check"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    checks_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    blocking_fail_count: int

    checks: list[dict[str, Any]] = Field(default_factory=list)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_compliance_config() -> ComplianceConfig:
    return ComplianceConfig(
        enabled=env_bool("OPS_CHECK_ENABLED", True),
        output_dir=Path(os.getenv("OPS_OUTPUT_DIR", "artifacts/ops")),
        operator_country=os.getenv("OPS_OPERATOR_COUNTRY", "BR"),
        require_legal_review_before_live=env_bool("OPS_REQUIRE_LEGAL_REVIEW_BEFORE_LIVE", True),
        legal_review_approved=env_bool("OPS_LEGAL_REVIEW_APPROVED", False),
        require_paper_trading=env_bool("OPS_REQUIRE_PAPER_TRADING", True),
        require_backtest_positive=env_bool("OPS_REQUIRE_BACKTEST_POSITIVE", True),
        require_calibration_valid=env_bool("OPS_REQUIRE_CALIBRATION_VALID", True),
        require_kill_switch_tested=env_bool("OPS_REQUIRE_KILL_SWITCH_TESTED", True),
        require_alerts_enabled=env_bool("OPS_REQUIRE_ALERTS_ENABLED", True),
        require_observability_enabled=env_bool("OPS_REQUIRE_OBSERVABILITY_ENABLED", True),
        require_live_trading_disabled_by_default=env_bool("OPS_REQUIRE_LIVE_TRADING_DISABLED_BY_DEFAULT", True),
    )


def make_check(
    *,
    code: str,
    status: CheckStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> ComplianceCheckItem:
    return ComplianceCheckItem(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def latest_json_file(directory: str | Path, pattern: str) -> Path | None:
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


def check_live_trading_disabled(config: ComplianceConfig) -> ComplianceCheckItem:
    allow_live = env_bool("BINANCE_ALLOW_LIVE_TRADING", False)
    risk_allow_live = env_bool("RISK_ALLOW_LIVE_TRADING", False)
    execution_mode = os.getenv("BINANCE_EXECUTION_MODE", "paper").strip().lower()

    if not config.require_live_trading_disabled_by_default:
        return make_check(
            code="LIVE_TRADING_POLICY_NOT_REQUIRED",
            status="WARN",
            title="Live trading policy not required",
            message="A política de live trading desabilitado por padrão foi marcada como não obrigatória.",
            value={
                "BINANCE_ALLOW_LIVE_TRADING": allow_live,
                "RISK_ALLOW_LIVE_TRADING": risk_allow_live,
                "BINANCE_EXECUTION_MODE": execution_mode,
            },
        )

    if allow_live or risk_allow_live or execution_mode == "live":
        return make_check(
            code="LIVE_TRADING_NOT_BLOCKED",
            status="FAIL",
            title="Live trading não está bloqueado",
            message="Live trading precisa permanecer falso por padrão antes de revisão final.",
            value={
                "BINANCE_ALLOW_LIVE_TRADING": allow_live,
                "RISK_ALLOW_LIVE_TRADING": risk_allow_live,
                "BINANCE_EXECUTION_MODE": execution_mode,
            },
            expected={
                "BINANCE_ALLOW_LIVE_TRADING": False,
                "RISK_ALLOW_LIVE_TRADING": False,
                "BINANCE_EXECUTION_MODE": "paper/testnet",
            },
            blocking=True,
        )

    return make_check(
        code="LIVE_TRADING_BLOCKED",
        status="PASS",
        title="Live trading bloqueado",
        message="Live trading permanece bloqueado por padrão.",
        value={
            "BINANCE_ALLOW_LIVE_TRADING": allow_live,
            "RISK_ALLOW_LIVE_TRADING": risk_allow_live,
            "BINANCE_EXECUTION_MODE": execution_mode,
        },
        expected=False,
    )


def check_operator_country(config: ComplianceConfig) -> ComplianceCheckItem:
    country = config.operator_country.upper().strip()

    if not country:
        return make_check(
            code="OPERATOR_COUNTRY_MISSING",
            status="WARN",
            title="Jurisdição não configurada",
            message="OPS_OPERATOR_COUNTRY não foi configurado.",
            value=country,
        )

    if country == "BR":
        return make_check(
            code="OPERATOR_COUNTRY_BR",
            status="WARN",
            title="Operador no Brasil",
            message="Antes de capital real, valide a situação jurídica atual com parecer formal.",
            value=country,
            expected="legal_review_before_live",
        )

    return make_check(
        code="OPERATOR_COUNTRY_CONFIGURED",
        status="PASS",
        title="Jurisdição configurada",
        message="OPS_OPERATOR_COUNTRY está configurado.",
        value=country,
    )


def check_legal_review(config: ComplianceConfig) -> ComplianceCheckItem:
    if not config.require_legal_review_before_live:
        return make_check(
            code="LEGAL_REVIEW_NOT_REQUIRED",
            status="WARN",
            title="Revisão jurídica não obrigatória",
            message="OPS_REQUIRE_LEGAL_REVIEW_BEFORE_LIVE está falso.",
            value=False,
        )

    if config.legal_review_approved:
        return make_check(
            code="LEGAL_REVIEW_APPROVED",
            status="PASS",
            title="Revisão jurídica aprovada",
            message="OPS_LEGAL_REVIEW_APPROVED está verdadeiro.",
            value=True,
        )

    return make_check(
        code="LEGAL_REVIEW_PENDING",
        status="WARN",
        title="Revisão jurídica pendente",
        message="Antes de capital real, obtenha parecer jurídico formal.",
        value=False,
        expected=True,
    )


def check_paper_trading_artifacts(config: ComplianceConfig) -> ComplianceCheckItem:
    if not config.require_paper_trading:
        return make_check(
            code="PAPER_TRADING_NOT_REQUIRED",
            status="WARN",
            title="Paper trading não obrigatório",
            message="OPS_REQUIRE_PAPER_TRADING está falso.",
        )

    latest = latest_json_file("artifacts/paper_trading", "*_summary.json")

    if latest is None:
        return make_check(
            code="PAPER_TRADING_REPORT_MISSING",
            status="WARN",
            title="Relatório de paper trading não encontrado",
            message="Nenhum summary de paper trading foi encontrado em artifacts/paper_trading.",
            expected="*_summary.json",
        )

    return make_check(
        code="PAPER_TRADING_REPORT_FOUND",
        status="PASS",
        title="Relatório de paper trading encontrado",
        message="Existe pelo menos um relatório de paper trading.",
        value=str(latest),
    )


def check_full_backtest_positive(config: ComplianceConfig) -> ComplianceCheckItem:
    if not config.require_backtest_positive:
        return make_check(
            code="BACKTEST_POSITIVE_NOT_REQUIRED",
            status="WARN",
            title="Backtest positivo não obrigatório",
            message="OPS_REQUIRE_BACKTEST_POSITIVE está falso.",
        )

    latest = latest_json_file("artifacts/full_backtest", "*_summary.json")
    payload = load_json(latest)

    if payload is None:
        return make_check(
            code="FULL_BACKTEST_REPORT_MISSING",
            status="WARN",
            title="Relatório de full backtest não encontrado",
            message="Nenhum summary de full backtest foi encontrado.",
            expected="*_summary.json",
        )

    metrics = payload.get("metrics") or {}
    net_pnl = float(metrics.get("net_pnl_usd", 0.0))
    roi = float(metrics.get("roi_pct", 0.0))

    if net_pnl > 0 and roi > 0:
        return make_check(
            code="FULL_BACKTEST_POSITIVE",
            status="PASS",
            title="Full backtest positivo",
            message="O último backtest possui net PnL e ROI positivos.",
            value={"net_pnl_usd": net_pnl, "roi_pct": roi, "file": str(latest)},
        )

    return make_check(
        code="FULL_BACKTEST_NOT_POSITIVE",
        status="WARN",
        title="Full backtest não positivo",
        message="O último backtest não possui net PnL e ROI positivos.",
        value={"net_pnl_usd": net_pnl, "roi_pct": roi, "file": str(latest)},
        expected={"net_pnl_usd": ">0", "roi_pct": ">0"},
    )


def check_calibration_valid(config: ComplianceConfig) -> ComplianceCheckItem:
    if not config.require_calibration_valid:
        return make_check(
            code="CALIBRATION_NOT_REQUIRED",
            status="WARN",
            title="Calibração não obrigatória",
            message="OPS_REQUIRE_CALIBRATION_VALID está falso.",
        )

    latest = latest_json_file("artifacts/model_evaluation", "*.json")
    payload = load_json(latest)

    if payload is None:
        return make_check(
            code="CALIBRATION_REPORT_MISSING",
            status="WARN",
            title="Relatório de calibração não encontrado",
            message="Nenhum relatório de calibração foi encontrado.",
            expected="*.json",
        )

    brier = float(payload.get("brier_score", 1.0))
    ece = float(payload.get("expected_calibration_error", 1.0))

    brier_limit = float(os.getenv("ALERTS_MAX_BRIER_SCORE", "0.25"))
    ece_limit = float(os.getenv("ALERTS_MAX_ECE", "0.15"))

    if brier <= brier_limit and ece <= ece_limit:
        return make_check(
            code="CALIBRATION_VALID",
            status="PASS",
            title="Calibração válida",
            message="Brier Score e ECE estão dentro dos limites.",
            value={"brier_score": brier, "ece": ece, "file": str(latest)},
            expected={"brier_score": f"<={brier_limit}", "ece": f"<={ece_limit}"},
        )

    return make_check(
        code="CALIBRATION_OUTSIDE_LIMITS",
        status="WARN",
        title="Calibração fora dos limites",
        message="Brier Score ou ECE estão acima dos limites.",
        value={"brier_score": brier, "ece": ece, "file": str(latest)},
        expected={"brier_score": f"<={brier_limit}", "ece": f"<={ece_limit}"},
    )


def check_kill_switch_configured(config: ComplianceConfig) -> ComplianceCheckItem:
    if not config.require_kill_switch_tested:
        return make_check(
            code="KILL_SWITCH_NOT_REQUIRED",
            status="WARN",
            title="Kill switch não obrigatório",
            message="OPS_REQUIRE_KILL_SWITCH_TESTED está falso.",
        )

    enabled = env_bool("CANCEL_ORDER_CANCEL_ON_KILL_SWITCH", True)

    if enabled:
        return make_check(
            code="KILL_SWITCH_CONFIGURED",
            status="PASS",
            title="Kill switch configurado",
            message="CANCEL_ORDER_CANCEL_ON_KILL_SWITCH está ativo.",
            value=True,
        )

    return make_check(
        code="KILL_SWITCH_NOT_CONFIGURED",
        status="FAIL",
        title="Kill switch não configurado",
        message="O cancelamento por kill switch precisa estar ativo.",
        value=False,
        expected=True,
        blocking=True,
    )


def check_alerts_enabled(config: ComplianceConfig) -> ComplianceCheckItem:
    if not config.require_alerts_enabled:
        return make_check(
            code="ALERTS_NOT_REQUIRED",
            status="WARN",
            title="Alertas não obrigatórios",
            message="OPS_REQUIRE_ALERTS_ENABLED está falso.",
        )

    enabled = env_bool("ALERTS_ENABLED", True)

    if enabled:
        return make_check(
            code="ALERTS_ENABLED",
            status="PASS",
            title="Alertas habilitados",
            message="ALERTS_ENABLED está verdadeiro.",
            value=True,
        )

    return make_check(
        code="ALERTS_DISABLED",
        status="FAIL",
        title="Alertas desabilitados",
        message="Alertas precisam estar habilitados para operação contínua.",
        value=False,
        expected=True,
        blocking=True,
    )


def check_observability_enabled(config: ComplianceConfig) -> ComplianceCheckItem:
    if not config.require_observability_enabled:
        return make_check(
            code="OBSERVABILITY_NOT_REQUIRED",
            status="WARN",
            title="Observabilidade não obrigatória",
            message="OPS_REQUIRE_OBSERVABILITY_ENABLED está falso.",
        )

    enabled = env_bool("OBSERVABILITY_ENABLED", True)

    if enabled:
        return make_check(
            code="OBSERVABILITY_ENABLED",
            status="PASS",
            title="Observabilidade habilitada",
            message="OBSERVABILITY_ENABLED está verdadeiro.",
            value=True,
        )

    return make_check(
        code="OBSERVABILITY_DISABLED",
        status="FAIL",
        title="Observabilidade desabilitada",
        message="Observabilidade precisa estar habilitada.",
        value=False,
        expected=True,
        blocking=True,
    )


def run_compliance_checks(config: ComplianceConfig | None = None) -> ComplianceReport:
    resolved_config = config or load_compliance_config()

    checks = [
        check_live_trading_disabled(resolved_config),
        check_operator_country(resolved_config),
        check_legal_review(resolved_config),
        check_paper_trading_artifacts(resolved_config),
        check_full_backtest_positive(resolved_config),
        check_calibration_valid(resolved_config),
        check_kill_switch_configured(resolved_config),
        check_alerts_enabled(resolved_config),
        check_observability_enabled(resolved_config),
    ]

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0

    return ComplianceReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_compliance_report(
    report: ComplianceReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "compliance_latest",
) -> Path:
    config = load_compliance_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path