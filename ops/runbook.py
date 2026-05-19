"""
Operational runbook / warm-up / pre-live checks.

Responsabilidades:
- Consolidar critérios objetivos para paper/testnet/live.
- Avaliar readiness operacional.
- Gerar relatório auditável.
- Bloquear live quando critérios mínimos falham.

Este módulo NÃO habilita live trading.
Este módulo NÃO envia ordens.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ops.compliance_check import run_compliance_checks
from ops.security_check import run_security_checks


load_dotenv()


RunbookStage = Literal["paper", "testnet", "live"]
StepStatus = Literal["PASS", "WARN", "FAIL"]


class RunbookConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_dir: Path = Path("artifacts/ops")

    default_stage: RunbookStage = "testnet"

    min_paper_trading_days: int = 14
    min_testnet_days: int = 14

    min_paper_trades: int = 50
    min_testnet_trades: int = 50

    min_fill_rate: float = 0.60
    min_profit_factor: float = 1.10
    min_sharpe: float = 0.50

    max_drawdown_pct: float = 0.20
    max_ece: float = 0.15
    max_brier_score: float = 0.25

    require_ops_check_pass: bool = True
    require_security_check_pass: bool = True
    require_compliance_check_pass: bool = False

    require_legal_review_for_live: bool = True
    require_testnet_for_live: bool = True
    require_live_trading_disabled_during_check: bool = True


class RunbookStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: StepStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class RunbookInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    paper_days_completed: int = 0
    testnet_days_completed: int = 0

    paper_trades_count: int = 0
    testnet_trades_count: int = 0

    paper_fill_rate: float | None = None
    testnet_fill_rate: float | None = None

    backtest_profit_factor: float | None = None
    backtest_sharpe: float | None = None
    backtest_max_drawdown_pct: float | None = None
    backtest_net_pnl_usd: float | None = None

    calibration_ece: float | None = None
    calibration_brier_score: float | None = None

    ops_check_passed: bool | None = None
    security_check_passed: bool | None = None
    compliance_check_passed: bool | None = None

    legal_review_approved: bool = False
    testnet_completed: bool = False

    binance_allow_live_trading: bool = False
    risk_allow_live_trading: bool = False
    binance_execution_mode: str = "paper"


class RunbookReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "operational_runbook"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    stage: RunbookStage
    passed: bool
    status: str

    steps_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    blocking_fail_count: int

    steps: list[dict[str, Any]] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_runbook_config() -> RunbookConfig:
    stage = os.getenv("RUNBOOK_DEFAULT_STAGE", "testnet").strip().lower()

    if stage not in {"paper", "testnet", "live"}:
        stage = "testnet"

    return RunbookConfig(
        enabled=env_bool("RUNBOOK_ENABLED", True),
        output_dir=Path(os.getenv("RUNBOOK_OUTPUT_DIR", "artifacts/ops")),
        default_stage=stage,  # type: ignore[arg-type]
        min_paper_trading_days=env_int("RUNBOOK_MIN_PAPER_TRADING_DAYS", 14),
        min_testnet_days=env_int("RUNBOOK_MIN_TESTNET_DAYS", 14),
        min_paper_trades=env_int("RUNBOOK_MIN_PAPER_TRADES", 50),
        min_testnet_trades=env_int("RUNBOOK_MIN_TESTNET_TRADES", 50),
        min_fill_rate=env_float("RUNBOOK_MIN_FILL_RATE", 0.60),
        min_profit_factor=env_float("RUNBOOK_MIN_PROFIT_FACTOR", 1.10),
        min_sharpe=env_float("RUNBOOK_MIN_SHARPE", 0.50),
        max_drawdown_pct=env_float("RUNBOOK_MAX_DRAWDOWN_PCT", 0.20),
        max_ece=env_float("RUNBOOK_MAX_ECE", 0.15),
        max_brier_score=env_float("RUNBOOK_MAX_BRIER_SCORE", 0.25),
        require_ops_check_pass=env_bool("RUNBOOK_REQUIRE_OPS_CHECK_PASS", True),
        require_security_check_pass=env_bool("RUNBOOK_REQUIRE_SECURITY_CHECK_PASS", True),
        require_compliance_check_pass=env_bool("RUNBOOK_REQUIRE_COMPLIANCE_CHECK_PASS", False),
        require_legal_review_for_live=env_bool("RUNBOOK_REQUIRE_LEGAL_REVIEW_FOR_LIVE", True),
        require_testnet_for_live=env_bool("RUNBOOK_REQUIRE_TESTNET_FOR_LIVE", True),
        require_live_trading_disabled_during_check=env_bool("RUNBOOK_REQUIRE_LIVE_TRADING_DISABLED_DURING_CHECK", True),
    )


def make_step(
    *,
    code: str,
    status: StepStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> RunbookStep:
    return RunbookStep(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
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


def extract_inputs_from_artifacts() -> RunbookInputs:
    paper_report = load_json(latest_file("artifacts/paper_trading", "*_summary.json"))
    backtest_report = load_json(latest_file("artifacts/full_backtest", "*_summary.json"))
    calibration_report = load_json(latest_file("artifacts/model_evaluation", "*.json"))

    compliance = run_compliance_checks()
    security = run_security_checks()

    paper_metrics = (paper_report or {}).get("metrics") or {}
    backtest_metrics = (backtest_report or {}).get("metrics") or {}

    return RunbookInputs(
        paper_trades_count=int(paper_metrics.get("simulated_trades", 0) or paper_metrics.get("routed_orders", 0) or 0),
        paper_fill_rate=safe_float(paper_metrics.get("fill_rate")),
        backtest_profit_factor=safe_float(backtest_metrics.get("profit_factor")),
        backtest_sharpe=safe_float(backtest_metrics.get("sharpe")),
        backtest_max_drawdown_pct=safe_float(backtest_metrics.get("max_drawdown_pct")),
        backtest_net_pnl_usd=safe_float(backtest_metrics.get("net_pnl_usd")),
        calibration_ece=safe_float((calibration_report or {}).get("expected_calibration_error")),
        calibration_brier_score=safe_float((calibration_report or {}).get("brier_score")),
        compliance_check_passed=compliance.passed,
        security_check_passed=security.passed,
        legal_review_approved=env_bool("OPS_LEGAL_REVIEW_APPROVED", False),
        binance_allow_live_trading=env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
        risk_allow_live_trading=env_bool("RISK_ALLOW_LIVE_TRADING", False),
        binance_execution_mode=os.getenv("BINANCE_EXECUTION_MODE", "paper").strip().lower(),
    )


def evaluate_paper_requirements(
    *,
    inputs: RunbookInputs,
    config: RunbookConfig,
    stage: RunbookStage,
) -> list[RunbookStep]:
    steps: list[RunbookStep] = []

    if stage in {"testnet", "live"}:
        if inputs.paper_days_completed >= config.min_paper_trading_days:
            steps.append(
                make_step(
                    code="PAPER_DAYS_OK",
                    status="PASS",
                    title="Paper trading days completed",
                    message="Quantidade mínima de dias em paper trading atingida.",
                    value=inputs.paper_days_completed,
                    expected=f">={config.min_paper_trading_days}",
                )
            )
        else:
            steps.append(
                make_step(
                    code="PAPER_DAYS_INSUFFICIENT",
                    status="WARN",
                    title="Paper trading insuficiente",
                    message="Ainda não há dias suficientes de paper trading para avançar.",
                    value=inputs.paper_days_completed,
                    expected=f">={config.min_paper_trading_days}",
                    blocking=(stage == "live"),
                )
            )

        if inputs.paper_trades_count >= config.min_paper_trades:
            steps.append(
                make_step(
                    code="PAPER_TRADES_OK",
                    status="PASS",
                    title="Paper trades suficientes",
                    message="Quantidade mínima de trades simulados atingida.",
                    value=inputs.paper_trades_count,
                    expected=f">={config.min_paper_trades}",
                )
            )
        else:
            steps.append(
                make_step(
                    code="PAPER_TRADES_INSUFFICIENT",
                    status="WARN",
                    title="Paper trades insuficientes",
                    message="Quantidade de trades em paper ainda está abaixo do mínimo.",
                    value=inputs.paper_trades_count,
                    expected=f">={config.min_paper_trades}",
                    blocking=(stage == "live"),
                )
            )

        if inputs.paper_fill_rate is not None and inputs.paper_fill_rate >= config.min_fill_rate:
            steps.append(
                make_step(
                    code="PAPER_FILL_RATE_OK",
                    status="PASS",
                    title="Paper fill rate OK",
                    message="Fill rate de paper trading está acima do mínimo.",
                    value=inputs.paper_fill_rate,
                    expected=f">={config.min_fill_rate}",
                )
            )
        else:
            steps.append(
                make_step(
                    code="PAPER_FILL_RATE_LOW",
                    status="WARN",
                    title="Paper fill rate baixo",
                    message="Fill rate de paper trading está abaixo do mínimo ou ausente.",
                    value=inputs.paper_fill_rate,
                    expected=f">={config.min_fill_rate}",
                    blocking=(stage == "live"),
                )
            )

    return steps


def evaluate_backtest_requirements(
    *,
    inputs: RunbookInputs,
    config: RunbookConfig,
) -> list[RunbookStep]:
    steps: list[RunbookStep] = []

    if inputs.backtest_net_pnl_usd is not None and inputs.backtest_net_pnl_usd > 0:
        steps.append(
            make_step(
                code="BACKTEST_PNL_POSITIVE",
                status="PASS",
                title="Backtest PnL positivo",
                message="Backtest possui PnL líquido positivo.",
                value=inputs.backtest_net_pnl_usd,
                expected=">0",
            )
        )
    else:
        steps.append(
            make_step(
                code="BACKTEST_PNL_NOT_POSITIVE",
                status="WARN",
                title="Backtest PnL não positivo",
                message="Backtest não possui PnL positivo ou métrica está ausente.",
                value=inputs.backtest_net_pnl_usd,
                expected=">0",
                blocking=False,
            )
        )

    if inputs.backtest_profit_factor is not None and inputs.backtest_profit_factor >= config.min_profit_factor:
        steps.append(
            make_step(
                code="BACKTEST_PROFIT_FACTOR_OK",
                status="PASS",
                title="Profit factor OK",
                message="Profit factor acima do mínimo.",
                value=inputs.backtest_profit_factor,
                expected=f">={config.min_profit_factor}",
            )
        )
    else:
        steps.append(
            make_step(
                code="BACKTEST_PROFIT_FACTOR_LOW",
                status="WARN",
                title="Profit factor baixo",
                message="Profit factor abaixo do mínimo ou ausente.",
                value=inputs.backtest_profit_factor,
                expected=f">={config.min_profit_factor}",
            )
        )

    if inputs.backtest_max_drawdown_pct is not None and inputs.backtest_max_drawdown_pct <= config.max_drawdown_pct:
        steps.append(
            make_step(
                code="BACKTEST_DRAWDOWN_OK",
                status="PASS",
                title="Drawdown OK",
                message="Max drawdown dentro do limite.",
                value=inputs.backtest_max_drawdown_pct,
                expected=f"<={config.max_drawdown_pct}",
            )
        )
    else:
        steps.append(
            make_step(
                code="BACKTEST_DRAWDOWN_HIGH",
                status="WARN",
                title="Drawdown alto",
                message="Max drawdown acima do limite ou ausente.",
                value=inputs.backtest_max_drawdown_pct,
                expected=f"<={config.max_drawdown_pct}",
            )
        )

    if inputs.backtest_sharpe is not None and inputs.backtest_sharpe >= config.min_sharpe:
        steps.append(
            make_step(
                code="BACKTEST_SHARPE_OK",
                status="PASS",
                title="Sharpe OK",
                message="Sharpe acima do mínimo.",
                value=inputs.backtest_sharpe,
                expected=f">={config.min_sharpe}",
            )
        )
    else:
        steps.append(
            make_step(
                code="BACKTEST_SHARPE_LOW",
                status="WARN",
                title="Sharpe baixo",
                message="Sharpe abaixo do mínimo ou ausente.",
                value=inputs.backtest_sharpe,
                expected=f">={config.min_sharpe}",
            )
        )

    return steps


def evaluate_calibration_requirements(
    *,
    inputs: RunbookInputs,
    config: RunbookConfig,
) -> list[RunbookStep]:
    steps: list[RunbookStep] = []

    if inputs.calibration_ece is not None and inputs.calibration_ece <= config.max_ece:
        steps.append(
            make_step(
                code="CALIBRATION_ECE_OK",
                status="PASS",
                title="ECE OK",
                message="Expected Calibration Error dentro do limite.",
                value=inputs.calibration_ece,
                expected=f"<={config.max_ece}",
            )
        )
    else:
        steps.append(
            make_step(
                code="CALIBRATION_ECE_HIGH",
                status="WARN",
                title="ECE alto",
                message="ECE acima do limite ou ausente.",
                value=inputs.calibration_ece,
                expected=f"<={config.max_ece}",
            )
        )

    if inputs.calibration_brier_score is not None and inputs.calibration_brier_score <= config.max_brier_score:
        steps.append(
            make_step(
                code="CALIBRATION_BRIER_OK",
                status="PASS",
                title="Brier Score OK",
                message="Brier Score dentro do limite.",
                value=inputs.calibration_brier_score,
                expected=f"<={config.max_brier_score}",
            )
        )
    else:
        steps.append(
            make_step(
                code="CALIBRATION_BRIER_HIGH",
                status="WARN",
                title="Brier Score alto",
                message="Brier Score acima do limite ou ausente.",
                value=inputs.calibration_brier_score,
                expected=f"<={config.max_brier_score}",
            )
        )

    return steps


def evaluate_ops_requirements(
    *,
    inputs: RunbookInputs,
    config: RunbookConfig,
) -> list[RunbookStep]:
    steps: list[RunbookStep] = []

    if config.require_security_check_pass:
        if inputs.security_check_passed is True:
            steps.append(
                make_step(
                    code="SECURITY_CHECK_PASS",
                    status="PASS",
                    title="Security check aprovado",
                    message="Security check passou.",
                    value=True,
                    expected=True,
                )
            )
        else:
            steps.append(
                make_step(
                    code="SECURITY_CHECK_FAIL",
                    status="FAIL",
                    title="Security check falhou",
                    message="Security check não passou.",
                    value=inputs.security_check_passed,
                    expected=True,
                    blocking=True,
                )
            )

    if config.require_compliance_check_pass:
        if inputs.compliance_check_passed is True:
            steps.append(
                make_step(
                    code="COMPLIANCE_CHECK_PASS",
                    status="PASS",
                    title="Compliance check aprovado",
                    message="Compliance check passou.",
                    value=True,
                    expected=True,
                )
            )
        else:
            steps.append(
                make_step(
                    code="COMPLIANCE_CHECK_FAIL",
                    status="FAIL",
                    title="Compliance check falhou",
                    message="Compliance check não passou.",
                    value=inputs.compliance_check_passed,
                    expected=True,
                    blocking=True,
                )
            )

    return steps


def evaluate_live_requirements(
    *,
    inputs: RunbookInputs,
    config: RunbookConfig,
    stage: RunbookStage,
) -> list[RunbookStep]:
    if stage != "live":
        return []

    steps: list[RunbookStep] = []

    if config.require_testnet_for_live:
        if inputs.testnet_completed and inputs.testnet_days_completed >= config.min_testnet_days and inputs.testnet_trades_count >= config.min_testnet_trades:
            steps.append(
                make_step(
                    code="TESTNET_COMPLETED_FOR_LIVE",
                    status="PASS",
                    title="Testnet concluída",
                    message="Critérios mínimos de testnet foram atingidos.",
                    value={
                        "testnet_completed": inputs.testnet_completed,
                        "days": inputs.testnet_days_completed,
                        "trades": inputs.testnet_trades_count,
                    },
                )
            )
        else:
            steps.append(
                make_step(
                    code="TESTNET_NOT_COMPLETED_FOR_LIVE",
                    status="FAIL",
                    title="Testnet insuficiente para live",
                    message="Live não deve ser considerada sem período mínimo de testnet.",
                    value={
                        "testnet_completed": inputs.testnet_completed,
                        "days": inputs.testnet_days_completed,
                        "trades": inputs.testnet_trades_count,
                    },
                    expected={
                        "testnet_completed": True,
                        "days": f">={config.min_testnet_days}",
                        "trades": f">={config.min_testnet_trades}",
                    },
                    blocking=True,
                )
            )

    if config.require_legal_review_for_live:
        if inputs.legal_review_approved:
            steps.append(
                make_step(
                    code="LEGAL_REVIEW_APPROVED_FOR_LIVE",
                    status="PASS",
                    title="Revisão jurídica aprovada",
                    message="Revisão jurídica aprovada para avaliar live.",
                    value=True,
                    expected=True,
                )
            )
        else:
            steps.append(
                make_step(
                    code="LEGAL_REVIEW_REQUIRED_FOR_LIVE",
                    status="FAIL",
                    title="Revisão jurídica obrigatória",
                    message="Live trading não deve ser considerado sem parecer jurídico formal.",
                    value=False,
                    expected=True,
                    blocking=True,
                )
            )

    return steps


def evaluate_live_trading_flags(
    *,
    inputs: RunbookInputs,
    config: RunbookConfig,
) -> list[RunbookStep]:
    if not config.require_live_trading_disabled_during_check:
        return []

    live_enabled = (
        inputs.binance_allow_live_trading
        or inputs.risk_allow_live_trading
        or inputs.binance_execution_mode == "live"
    )

    if live_enabled:
        return [
            make_step(
                code="LIVE_TRADING_ENABLED_DURING_CHECK",
                status="FAIL",
                title="Live trading habilitado durante check",
                message="Live trading precisa estar desabilitado durante o pre-live check.",
                value={
                    "binance_allow_live_trading": inputs.binance_allow_live_trading,
                    "risk_allow_live_trading": inputs.risk_allow_live_trading,
                    "binance_execution_mode": inputs.binance_execution_mode,
                },
                expected="live disabled",
                blocking=True,
            )
        ]

    return [
        make_step(
            code="LIVE_TRADING_DISABLED_DURING_CHECK",
            status="PASS",
            title="Live trading desabilitado durante check",
            message="Flags de live trading permanecem desabilitadas.",
            value={
                "binance_allow_live_trading": inputs.binance_allow_live_trading,
                "risk_allow_live_trading": inputs.risk_allow_live_trading,
                "binance_execution_mode": inputs.binance_execution_mode,
            },
        )
    ]


def build_runbook_report(
    *,
    stage: RunbookStage | None = None,
    inputs: RunbookInputs | dict[str, Any] | None = None,
    config: RunbookConfig | None = None,
) -> RunbookReport:
    resolved_config = config or load_runbook_config()
    resolved_stage = stage or resolved_config.default_stage

    if inputs is None:
        resolved_inputs = extract_inputs_from_artifacts()
    elif isinstance(inputs, RunbookInputs):
        resolved_inputs = inputs
    else:
        resolved_inputs = RunbookInputs.model_validate(inputs)

    if not resolved_config.enabled:
        step = make_step(
            code="RUNBOOK_DISABLED",
            status="FAIL",
            title="Runbook desabilitado",
            message="RUNBOOK_ENABLED está falso.",
            value=False,
            expected=True,
            blocking=True,
        )

        return RunbookReport(
            stage=resolved_stage,
            passed=False,
            status="FAIL",
            steps_count=1,
            pass_count=0,
            warn_count=0,
            fail_count=1,
            blocking_fail_count=1,
            steps=[step.model_dump(mode="json")],
            inputs=resolved_inputs.model_dump(mode="json"),
        )

    steps: list[RunbookStep] = []
    steps.extend(evaluate_live_trading_flags(inputs=resolved_inputs, config=resolved_config))
    steps.extend(evaluate_paper_requirements(inputs=resolved_inputs, config=resolved_config, stage=resolved_stage))
    steps.extend(evaluate_backtest_requirements(inputs=resolved_inputs, config=resolved_config))
    steps.extend(evaluate_calibration_requirements(inputs=resolved_inputs, config=resolved_config))
    steps.extend(evaluate_ops_requirements(inputs=resolved_inputs, config=resolved_config))
    steps.extend(evaluate_live_requirements(inputs=resolved_inputs, config=resolved_config, stage=resolved_stage))

    pass_count = sum(1 for item in steps if item.status == "PASS")
    warn_count = sum(1 for item in steps if item.status == "WARN")
    fail_count = sum(1 for item in steps if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in steps if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0

    return RunbookReport(
        stage=resolved_stage,
        passed=passed,
        status="PASS" if passed else "FAIL",
        steps_count=len(steps),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        steps=[item.model_dump(mode="json") for item in steps],
        inputs=resolved_inputs.model_dump(mode="json"),
    )


def export_runbook_report(
    report: RunbookReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "runbook_latest",
) -> Path:
    config = load_runbook_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path