from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


StrategyHealthStatus = Literal["HEALTHY", "WATCH", "BLOCKED"]


class StrategyHealthInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    strategy_name: str = "btc_futures_strategy"
    symbol: str = "BTCUSDT"
    timeframe: str | None = None

    trades_count: int = 0
    net_pnl_usd: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float | None = None
    win_rate: float | None = None

    fill_rate: float | None = None
    rejection_rate: float | None = None
    cancel_rate: float | None = None

    expected_calibration_error: float | None = None
    ood_rate: float | None = None

    discipline_score: float | None = None
    risk_state_status: str | None = "OK"


class StrategyHealthReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "strategy_health"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    strategy_name: str
    symbol: str
    timeframe: str | None = None

    status: StrategyHealthStatus
    passed: bool
    health_score: float

    component_scores: dict[str, float] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    input: dict[str, Any]


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def ratio_score(value: float | None, target: float, *, higher_is_better: bool = True) -> float:
    if value is None:
        return 0.5

    if target <= 0:
        return 1.0

    if higher_is_better:
        return clamp(value / target)

    return clamp(1.0 - (value / target))


def build_strategy_health_report(
    *,
    input_data: StrategyHealthInput | dict[str, Any],
) -> StrategyHealthReport:
    data = input_data if isinstance(input_data, StrategyHealthInput) else StrategyHealthInput.model_validate(input_data)

    min_score = env_float("STRATEGY_HEALTH_MIN_SCORE", 0.70)
    blocking_score = env_float("STRATEGY_HEALTH_BLOCKING_SCORE", 0.50)

    min_pf = env_float("STRATEGY_HEALTH_MIN_PROFIT_FACTOR", 1.10)
    min_win_rate = env_float("STRATEGY_HEALTH_MIN_WIN_RATE", 0.50)
    min_fill_rate = env_float("STRATEGY_HEALTH_MIN_FILL_RATE", 0.60)
    max_dd = env_float("STRATEGY_HEALTH_MAX_DRAWDOWN_PCT", 0.10)
    max_rejection = env_float("STRATEGY_HEALTH_MAX_REJECTION_RATE", 0.10)
    max_ece = env_float("STRATEGY_HEALTH_MAX_ECE", 0.15)
    max_ood = env_float("STRATEGY_HEALTH_MAX_OOD_RATE", 0.20)

    pnl_score = 1.0 if data.net_pnl_usd >= 0 else 0.25
    drawdown_score = ratio_score(data.max_drawdown_pct, max_dd, higher_is_better=False)
    profit_factor_score = ratio_score(data.profit_factor, min_pf)
    win_rate_score = ratio_score(data.win_rate, min_win_rate)
    fill_rate_score = ratio_score(data.fill_rate, min_fill_rate)
    rejection_score = ratio_score(data.rejection_rate, max_rejection, higher_is_better=False)
    ece_score = ratio_score(data.expected_calibration_error, max_ece, higher_is_better=False)
    ood_score = ratio_score(data.ood_rate, max_ood, higher_is_better=False)
    discipline_score = data.discipline_score if data.discipline_score is not None else 0.5

    component_scores = {
        "pnl": pnl_score,
        "drawdown": drawdown_score,
        "profit_factor": profit_factor_score,
        "win_rate": win_rate_score,
        "fill_rate": fill_rate_score,
        "rejection_rate": rejection_score,
        "calibration": ece_score,
        "ood": ood_score,
        "discipline": clamp(discipline_score),
    }

    weights = {
        "pnl": 0.10,
        "drawdown": 0.15,
        "profit_factor": 0.15,
        "win_rate": 0.10,
        "fill_rate": 0.10,
        "rejection_rate": 0.10,
        "calibration": 0.10,
        "ood": 0.10,
        "discipline": 0.10,
    }

    health_score = round(
        sum(component_scores[key] * weights[key] for key in component_scores),
        6,
    )

    blockers: list[str] = []
    warnings: list[str] = []

    if data.risk_state_status and data.risk_state_status != "OK":
        blockers.append("risk_state_not_ok")

    if data.max_drawdown_pct > max_dd:
        blockers.append("drawdown_above_limit")

    if data.expected_calibration_error is not None and data.expected_calibration_error > max_ece:
        warnings.append("ece_above_limit")

    if data.ood_rate is not None and data.ood_rate > max_ood:
        warnings.append("ood_rate_above_limit")

    if health_score < blocking_score:
        blockers.append("strategy_health_below_blocking_score")
    elif health_score < min_score:
        warnings.append("strategy_health_below_min_score")

    passed = not blockers and health_score >= min_score

    if blockers:
        status: StrategyHealthStatus = "BLOCKED"
    elif warnings:
        status = "WATCH"
    else:
        status = "HEALTHY"

    return StrategyHealthReport(
        strategy_name=data.strategy_name,
        symbol=data.symbol,
        timeframe=data.timeframe,
        status=status,
        passed=passed,
        health_score=health_score,
        component_scores=component_scores,
        blockers=blockers,
        warnings=warnings,
        input=data.model_dump(mode="json"),
    )


def export_strategy_health_report(
    report: StrategyHealthReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "strategy_health_latest",
) -> Path:
    path = Path(output_dir or os.getenv("STRATEGY_HEALTH_OUTPUT_DIR", "artifacts/governance"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path