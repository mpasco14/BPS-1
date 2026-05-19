"""
Model retraining protocol.

Responsabilidades:
- Avaliar se um modelo candidato pode ser promovido.
- Validar métricas mínimas de backtest e calibração.
- Comparar candidato contra modelo atual quando disponível.
- Impedir promoção automática por padrão.
- Gerar relatório auditável.

Este módulo NÃO treina modelo.
Este módulo NÃO substitui modelo em produção.
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
RetrainingDecision = Literal["APPROVED", "REJECTED"]


class RetrainingProtocolConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_dir: Path = Path("artifacts/ops")

    min_new_samples: int = 500
    max_ece: float = 0.15
    max_brier_score: float = 0.25
    min_profit_factor: float = 1.10
    min_sharpe: float = 0.50
    max_drawdown_pct: float = 0.20

    require_backtest_positive: bool = True
    require_calibration_valid: bool = True
    require_candidate_beats_current: bool = True

    allow_auto_promote: bool = False


class ModelValidationMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    model_version: str = "candidate"
    samples: int | None = None

    brier_score: float | None = None
    expected_calibration_error: float | None = None

    net_pnl_usd: float | None = None
    roi_pct: float | None = None
    profit_factor: float | None = None
    sharpe: float | None = None
    max_drawdown_pct: float | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrainingCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: CheckStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class RetrainingDecisionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "retraining_protocol"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    decision: RetrainingDecision
    passed: bool

    promotion_recommended: bool
    auto_promote_allowed: bool

    candidate: dict[str, Any]
    current: dict[str, Any] | None = None

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


def load_retraining_protocol_config() -> RetrainingProtocolConfig:
    return RetrainingProtocolConfig(
        enabled=env_bool("RETRAINING_PROTOCOL_ENABLED", True),
        output_dir=Path(os.getenv("RETRAINING_OUTPUT_DIR", "artifacts/ops")),
        min_new_samples=env_int("RETRAINING_MIN_NEW_SAMPLES", 500),
        max_ece=env_float("RETRAINING_MAX_ECE", 0.15),
        max_brier_score=env_float("RETRAINING_MAX_BRIER_SCORE", 0.25),
        min_profit_factor=env_float("RETRAINING_MIN_PROFIT_FACTOR", 1.10),
        min_sharpe=env_float("RETRAINING_MIN_SHARPE", 0.50),
        max_drawdown_pct=env_float("RETRAINING_MAX_DRAWDOWN_PCT", 0.20),
        require_backtest_positive=env_bool("RETRAINING_REQUIRE_BACKTEST_POSITIVE", True),
        require_calibration_valid=env_bool("RETRAINING_REQUIRE_CALIBRATION_VALID", True),
        require_candidate_beats_current=env_bool("RETRAINING_REQUIRE_CANDIDATE_BEATS_CURRENT", True),
        allow_auto_promote=env_bool("RETRAINING_ALLOW_AUTO_PROMOTE", False),
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
) -> RetrainingCheck:
    return RetrainingCheck(
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


def build_candidate_metrics_from_artifacts(
    *,
    model_version: str = "candidate_from_latest_artifacts",
) -> ModelValidationMetrics:
    calibration_path = latest_file("artifacts/model_evaluation", "*.json")
    backtest_path = latest_file("artifacts/full_backtest", "*_summary.json")

    calibration = load_json(calibration_path) or {}
    backtest = load_json(backtest_path) or {}
    backtest_metrics = backtest.get("metrics") or {}

    return ModelValidationMetrics(
        model_version=model_version,
        samples=int(calibration.get("samples", 0) or 0),
        brier_score=safe_float(calibration.get("brier_score")),
        expected_calibration_error=safe_float(calibration.get("expected_calibration_error")),
        net_pnl_usd=safe_float(backtest_metrics.get("net_pnl_usd")),
        roi_pct=safe_float(backtest_metrics.get("roi_pct")),
        profit_factor=safe_float(backtest_metrics.get("profit_factor")),
        sharpe=safe_float(backtest_metrics.get("sharpe")),
        max_drawdown_pct=safe_float(backtest_metrics.get("max_drawdown_pct")),
        metadata={
            "calibration_file": str(calibration_path) if calibration_path else None,
            "backtest_file": str(backtest_path) if backtest_path else None,
        },
    )


def evaluate_candidate_metrics(
    *,
    candidate: ModelValidationMetrics,
    config: RetrainingProtocolConfig,
) -> list[RetrainingCheck]:
    checks: list[RetrainingCheck] = []

    if not config.enabled:
        checks.append(
            make_check(
                code="RETRAINING_DISABLED",
                status="FAIL",
                title="Retraining protocol disabled",
                message="RETRAINING_PROTOCOL_ENABLED está falso.",
                value=False,
                expected=True,
                blocking=True,
            )
        )
        return checks

    if candidate.samples is not None and candidate.samples >= config.min_new_samples:
        checks.append(
            make_check(
                code="SAMPLES_OK",
                status="PASS",
                title="Amostras suficientes",
                message="Quantidade de amostras do candidato atingiu o mínimo.",
                value=candidate.samples,
                expected=f">={config.min_new_samples}",
            )
        )
    else:
        checks.append(
            make_check(
                code="SAMPLES_INSUFFICIENT",
                status="FAIL",
                title="Amostras insuficientes",
                message="Modelo candidato não tem amostras suficientes para promoção.",
                value=candidate.samples,
                expected=f">={config.min_new_samples}",
                blocking=True,
            )
        )

    if config.require_calibration_valid:
        if candidate.brier_score is not None and candidate.brier_score <= config.max_brier_score:
            checks.append(
                make_check(
                    code="BRIER_SCORE_OK",
                    status="PASS",
                    title="Brier Score OK",
                    message="Brier Score dentro do limite.",
                    value=candidate.brier_score,
                    expected=f"<={config.max_brier_score}",
                )
            )
        else:
            checks.append(
                make_check(
                    code="BRIER_SCORE_HIGH",
                    status="FAIL",
                    title="Brier Score alto",
                    message="Brier Score acima do limite ou ausente.",
                    value=candidate.brier_score,
                    expected=f"<={config.max_brier_score}",
                    blocking=True,
                )
            )

        if candidate.expected_calibration_error is not None and candidate.expected_calibration_error <= config.max_ece:
            checks.append(
                make_check(
                    code="ECE_OK",
                    status="PASS",
                    title="ECE OK",
                    message="Expected Calibration Error dentro do limite.",
                    value=candidate.expected_calibration_error,
                    expected=f"<={config.max_ece}",
                )
            )
        else:
            checks.append(
                make_check(
                    code="ECE_HIGH",
                    status="FAIL",
                    title="ECE alto",
                    message="Expected Calibration Error acima do limite ou ausente.",
                    value=candidate.expected_calibration_error,
                    expected=f"<={config.max_ece}",
                    blocking=True,
                )
            )

    if config.require_backtest_positive:
        if candidate.net_pnl_usd is not None and candidate.net_pnl_usd > 0:
            checks.append(
                make_check(
                    code="BACKTEST_PNL_POSITIVE",
                    status="PASS",
                    title="Backtest positivo",
                    message="Candidato possui PnL líquido positivo.",
                    value=candidate.net_pnl_usd,
                    expected=">0",
                )
            )
        else:
            checks.append(
                make_check(
                    code="BACKTEST_PNL_NOT_POSITIVE",
                    status="FAIL",
                    title="Backtest não positivo",
                    message="Modelo candidato não possui PnL líquido positivo.",
                    value=candidate.net_pnl_usd,
                    expected=">0",
                    blocking=True,
                )
            )

    if candidate.profit_factor is not None and candidate.profit_factor >= config.min_profit_factor:
        checks.append(
            make_check(
                code="PROFIT_FACTOR_OK",
                status="PASS",
                title="Profit factor OK",
                message="Profit factor acima do mínimo.",
                value=candidate.profit_factor,
                expected=f">={config.min_profit_factor}",
            )
        )
    else:
        checks.append(
            make_check(
                code="PROFIT_FACTOR_LOW",
                status="FAIL",
                title="Profit factor baixo",
                message="Profit factor abaixo do mínimo ou ausente.",
                value=candidate.profit_factor,
                expected=f">={config.min_profit_factor}",
                blocking=True,
            )
        )

    if candidate.sharpe is not None and candidate.sharpe >= config.min_sharpe:
        checks.append(
            make_check(
                code="SHARPE_OK",
                status="PASS",
                title="Sharpe OK",
                message="Sharpe acima do mínimo.",
                value=candidate.sharpe,
                expected=f">={config.min_sharpe}",
            )
        )
    else:
        checks.append(
            make_check(
                code="SHARPE_LOW",
                status="WARN",
                title="Sharpe baixo",
                message="Sharpe abaixo do mínimo ou ausente.",
                value=candidate.sharpe,
                expected=f">={config.min_sharpe}",
            )
        )

    if candidate.max_drawdown_pct is not None and candidate.max_drawdown_pct <= config.max_drawdown_pct:
        checks.append(
            make_check(
                code="DRAWDOWN_OK",
                status="PASS",
                title="Drawdown OK",
                message="Max drawdown dentro do limite.",
                value=candidate.max_drawdown_pct,
                expected=f"<={config.max_drawdown_pct}",
            )
        )
    else:
        checks.append(
            make_check(
                code="DRAWDOWN_HIGH",
                status="FAIL",
                title="Drawdown alto",
                message="Max drawdown acima do limite ou ausente.",
                value=candidate.max_drawdown_pct,
                expected=f"<={config.max_drawdown_pct}",
                blocking=True,
            )
        )

    return checks


def evaluate_candidate_vs_current(
    *,
    candidate: ModelValidationMetrics,
    current: ModelValidationMetrics | None,
    config: RetrainingProtocolConfig,
) -> list[RetrainingCheck]:
    if not config.require_candidate_beats_current:
        return [
            make_check(
                code="CANDIDATE_COMPARISON_NOT_REQUIRED",
                status="WARN",
                title="Comparação com modelo atual desabilitada",
                message="RETRAINING_REQUIRE_CANDIDATE_BEATS_CURRENT está falso.",
            )
        ]

    if current is None:
        return [
            make_check(
                code="CURRENT_MODEL_MISSING",
                status="WARN",
                title="Modelo atual ausente",
                message="Sem métricas do modelo atual para comparação.",
            )
        ]

    checks: list[RetrainingCheck] = []

    if candidate.expected_calibration_error is not None and current.expected_calibration_error is not None:
        if candidate.expected_calibration_error <= current.expected_calibration_error:
            checks.append(
                make_check(
                    code="CANDIDATE_ECE_BETTER_OR_EQUAL",
                    status="PASS",
                    title="ECE do candidato melhor ou igual",
                    message="Candidato tem ECE menor ou igual ao modelo atual.",
                    value=candidate.expected_calibration_error,
                    expected=f"<={current.expected_calibration_error}",
                )
            )
        else:
            checks.append(
                make_check(
                    code="CANDIDATE_ECE_WORSE",
                    status="FAIL",
                    title="ECE do candidato pior",
                    message="Candidato tem ECE pior que o modelo atual.",
                    value=candidate.expected_calibration_error,
                    expected=f"<={current.expected_calibration_error}",
                    blocking=True,
                )
            )

    if candidate.net_pnl_usd is not None and current.net_pnl_usd is not None:
        if candidate.net_pnl_usd >= current.net_pnl_usd:
            checks.append(
                make_check(
                    code="CANDIDATE_PNL_BETTER_OR_EQUAL",
                    status="PASS",
                    title="PnL do candidato melhor ou igual",
                    message="Candidato tem PnL maior ou igual ao modelo atual.",
                    value=candidate.net_pnl_usd,
                    expected=f">={current.net_pnl_usd}",
                )
            )
        else:
            checks.append(
                make_check(
                    code="CANDIDATE_PNL_WORSE",
                    status="FAIL",
                    title="PnL do candidato pior",
                    message="Candidato tem PnL pior que o modelo atual.",
                    value=candidate.net_pnl_usd,
                    expected=f">={current.net_pnl_usd}",
                    blocking=True,
                )
            )

    if not checks:
        checks.append(
            make_check(
                code="CANDIDATE_COMPARISON_INSUFFICIENT_DATA",
                status="WARN",
                title="Dados insuficientes para comparação",
                message="Não há métricas comparáveis suficientes entre candidato e modelo atual.",
            )
        )

    return checks


def evaluate_retraining_candidate(
    *,
    candidate: ModelValidationMetrics | dict[str, Any] | None = None,
    current: ModelValidationMetrics | dict[str, Any] | None = None,
    config: RetrainingProtocolConfig | None = None,
) -> RetrainingDecisionReport:
    resolved_config = config or load_retraining_protocol_config()

    if candidate is None:
        candidate_metrics = build_candidate_metrics_from_artifacts()
    elif isinstance(candidate, ModelValidationMetrics):
        candidate_metrics = candidate
    else:
        candidate_metrics = ModelValidationMetrics.model_validate(candidate)

    if current is None:
        current_metrics = None
    elif isinstance(current, ModelValidationMetrics):
        current_metrics = current
    else:
        current_metrics = ModelValidationMetrics.model_validate(current)

    checks: list[RetrainingCheck] = []
    checks.extend(
        evaluate_candidate_metrics(
            candidate=candidate_metrics,
            config=resolved_config,
        )
    )
    checks.extend(
        evaluate_candidate_vs_current(
            candidate=candidate_metrics,
            current=current_metrics,
            config=resolved_config,
        )
    )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0
    promotion_recommended = passed
    auto_promote_allowed = passed and resolved_config.allow_auto_promote

    return RetrainingDecisionReport(
        decision="APPROVED" if passed else "REJECTED",
        passed=passed,
        promotion_recommended=promotion_recommended,
        auto_promote_allowed=auto_promote_allowed,
        candidate=candidate_metrics.model_dump(mode="json"),
        current=current_metrics.model_dump(mode="json") if current_metrics else None,
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_retraining_report(
    report: RetrainingDecisionReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "retraining_latest",
) -> Path:
    config = load_retraining_protocol_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path