from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from data.learning_feedback_dataset import LearningFeedbackRow


load_dotenv()


RegimeRecommendationAction = Literal[
    "ALLOW",
    "REDUCE_EXPOSURE",
    "INCREASE_CONFIDENCE",
    "BLOCK",
    "COLLECT_MORE_DATA",
]


class RegimeOptimizationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live")

    min_samples: int = 10
    min_win_rate: float = 0.52
    min_avg_pnl_usd: float = 0.0
    max_drawdown_usd: float = 5.0

    reduce_exposure_win_rate: float = 0.45
    block_win_rate: float = 0.40
    block_avg_pnl_usd: float = -0.25


class RegimeRecommendation(BaseModel):
    model_config = ConfigDict(extra="allow")

    regime: str
    action: RegimeRecommendationAction
    reason: str

    samples: int
    trades: int
    win_rate: float | None = None
    avg_net_pnl_usd: float | None = None
    total_net_pnl_usd: float = 0.0
    max_drawdown_usd: float = 0.0

    recommended_min_confidence_adjustment: float = 0.0
    recommended_exposure_multiplier: float = 1.0


class RegimeOptimizationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "regime_optimization"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    regimes_count: int
    rows_count: int

    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    blocked_regimes: list[str] = Field(default_factory=list)
    reduced_exposure_regimes: list[str] = Field(default_factory=list)

    config: dict[str, Any] = Field(default_factory=dict)


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


def load_regime_optimization_config() -> RegimeOptimizationConfig:
    return RegimeOptimizationConfig(
        output_dir=Path(os.getenv("REGIME_OPTIMIZATION_OUTPUT_DIR", "artifacts/live")),
        min_samples=env_int("REGIME_OPTIMIZATION_MIN_SAMPLES", 10),
        min_win_rate=env_float("REGIME_OPTIMIZATION_MIN_WIN_RATE", 0.52),
        min_avg_pnl_usd=env_float("REGIME_OPTIMIZATION_MIN_AVG_PNL_USD", 0),
        max_drawdown_usd=env_float("REGIME_OPTIMIZATION_MAX_DRAWDOWN_USD", 5),
        reduce_exposure_win_rate=env_float("REGIME_OPTIMIZATION_REDUCE_EXPOSURE_WIN_RATE", 0.45),
        block_win_rate=env_float("REGIME_OPTIMIZATION_BLOCK_WIN_RATE", 0.40),
        block_avg_pnl_usd=env_float("REGIME_OPTIMIZATION_BLOCK_AVG_PNL_USD", -0.25),
    )


def calculate_max_drawdown(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)

    return round(max_drawdown, 8)


def average(values: list[float]) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


def build_regime_recommendation(
    *,
    regime: str,
    rows: list[LearningFeedbackRow],
    config: RegimeOptimizationConfig,
) -> RegimeRecommendation:
    trades = [row for row in rows if row.target is not None]
    wins = [row for row in trades if row.target == 1]
    pnl_values = [row.realized_net_pnl_usd or 0.0 for row in trades]

    samples = len(rows)
    trades_count = len(trades)
    win_rate = len(wins) / trades_count if trades_count else None
    avg_pnl = average(pnl_values)
    total_pnl = sum(pnl_values)
    max_drawdown = calculate_max_drawdown(pnl_values)

    if samples < config.min_samples:
        return RegimeRecommendation(
            regime=regime,
            action="COLLECT_MORE_DATA",
            reason="Amostra insuficiente para otimizar este regime.",
            samples=samples,
            trades=trades_count,
            win_rate=win_rate,
            avg_net_pnl_usd=avg_pnl,
            total_net_pnl_usd=round(total_pnl, 8),
            max_drawdown_usd=max_drawdown,
        )

    if win_rate is not None and win_rate <= config.block_win_rate and avg_pnl is not None and avg_pnl <= config.block_avg_pnl_usd:
        return RegimeRecommendation(
            regime=regime,
            action="BLOCK",
            reason="Win rate e PnL médio indicam regime não operável.",
            samples=samples,
            trades=trades_count,
            win_rate=win_rate,
            avg_net_pnl_usd=avg_pnl,
            total_net_pnl_usd=round(total_pnl, 8),
            max_drawdown_usd=max_drawdown,
            recommended_min_confidence_adjustment=0.10,
            recommended_exposure_multiplier=0.0,
        )

    if max_drawdown > config.max_drawdown_usd:
        return RegimeRecommendation(
            regime=regime,
            action="REDUCE_EXPOSURE",
            reason="Drawdown do regime acima do limite.",
            samples=samples,
            trades=trades_count,
            win_rate=win_rate,
            avg_net_pnl_usd=avg_pnl,
            total_net_pnl_usd=round(total_pnl, 8),
            max_drawdown_usd=max_drawdown,
            recommended_min_confidence_adjustment=0.05,
            recommended_exposure_multiplier=0.50,
        )

    if win_rate is not None and win_rate < config.reduce_exposure_win_rate:
        return RegimeRecommendation(
            regime=regime,
            action="REDUCE_EXPOSURE",
            reason="Win rate baixa; reduzir exposição neste regime.",
            samples=samples,
            trades=trades_count,
            win_rate=win_rate,
            avg_net_pnl_usd=avg_pnl,
            total_net_pnl_usd=round(total_pnl, 8),
            max_drawdown_usd=max_drawdown,
            recommended_min_confidence_adjustment=0.05,
            recommended_exposure_multiplier=0.50,
        )

    if win_rate is not None and win_rate < config.min_win_rate:
        return RegimeRecommendation(
            regime=regime,
            action="INCREASE_CONFIDENCE",
            reason="Win rate abaixo do ideal; exigir maior confiança.",
            samples=samples,
            trades=trades_count,
            win_rate=win_rate,
            avg_net_pnl_usd=avg_pnl,
            total_net_pnl_usd=round(total_pnl, 8),
            max_drawdown_usd=max_drawdown,
            recommended_min_confidence_adjustment=0.05,
            recommended_exposure_multiplier=0.75,
        )

    if avg_pnl is not None and avg_pnl < config.min_avg_pnl_usd:
        return RegimeRecommendation(
            regime=regime,
            action="INCREASE_CONFIDENCE",
            reason="PnL médio abaixo do mínimo; exigir edge/confiança maior.",
            samples=samples,
            trades=trades_count,
            win_rate=win_rate,
            avg_net_pnl_usd=avg_pnl,
            total_net_pnl_usd=round(total_pnl, 8),
            max_drawdown_usd=max_drawdown,
            recommended_min_confidence_adjustment=0.05,
            recommended_exposure_multiplier=0.75,
        )

    return RegimeRecommendation(
        regime=regime,
        action="ALLOW",
        reason="Regime dentro dos critérios mínimos.",
        samples=samples,
        trades=trades_count,
        win_rate=win_rate,
        avg_net_pnl_usd=avg_pnl,
        total_net_pnl_usd=round(total_pnl, 8),
        max_drawdown_usd=max_drawdown,
    )


def build_regime_optimization_report(
    *,
    rows: list[LearningFeedbackRow | dict[str, Any]],
    config: RegimeOptimizationConfig | None = None,
) -> RegimeOptimizationReport:
    resolved_config = config or load_regime_optimization_config()

    parsed_rows = [
        row if isinstance(row, LearningFeedbackRow) else LearningFeedbackRow.model_validate(row)
        for row in rows
    ]

    grouped: dict[str, list[LearningFeedbackRow]] = defaultdict(list)

    for row in parsed_rows:
        regime = row.regime or row.features.get("regime") or "unknown"
        grouped[str(regime)].append(row)

    recommendations = [
        build_regime_recommendation(
            regime=regime,
            rows=regime_rows,
            config=resolved_config,
        )
        for regime, regime_rows in sorted(grouped.items())
    ]

    blocked = [item.regime for item in recommendations if item.action == "BLOCK"]
    reduced = [item.regime for item in recommendations if item.action == "REDUCE_EXPOSURE"]

    passed = not blocked

    return RegimeOptimizationReport(
        passed=passed,
        status="PASS" if passed else "WARN",
        regimes_count=len(grouped),
        rows_count=len(parsed_rows),
        recommendations=[item.model_dump(mode="json") for item in recommendations],
        blocked_regimes=blocked,
        reduced_exposure_regimes=reduced,
        config=resolved_config.model_dump(mode="json"),
    )


def export_regime_optimization_report(
    report: RegimeOptimizationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "regime_optimization_latest",
) -> Path:
    config = load_regime_optimization_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path