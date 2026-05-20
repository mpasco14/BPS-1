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


ThresholdAction = Literal[
    "COLLECT_MORE_DATA",
    "KEEP_THRESHOLDS",
    "INCREASE_MIN_CONFIDENCE",
    "INCREASE_MIN_EDGE",
    "REDUCE_EXPOSURE",
    "PAUSE_TIMEFRAME",
]


class ThresholdReviewConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/governance")

    min_samples: int = 20
    min_win_rate: float = 0.52
    min_avg_net_pnl_usd: float = 0.0
    max_ece: float = 0.15

    current_min_confidence: dict[str, float] = Field(
        default_factory=lambda: {
            "5m": 0.65,
            "15m": 0.65,
            "1h": 0.65,
            "1D": 0.65,
        }
    )

    current_min_edge: dict[str, float] = Field(
        default_factory=lambda: {
            "5m": 0.03,
            "15m": 0.02,
            "1h": 0.015,
            "1D": 0.01,
        }
    )


class ThresholdRecommendation(BaseModel):
    model_config = ConfigDict(extra="allow")

    timeframe: str
    action: ThresholdAction
    reason: str

    samples: int
    trades: int
    win_rate: float | None = None
    avg_net_pnl_usd: float | None = None
    avg_confidence: float | None = None
    avg_expected_value_usd: float | None = None

    current_min_confidence: float | None = None
    recommended_min_confidence: float | None = None

    current_min_edge: float | None = None
    recommended_min_edge: float | None = None


class ThresholdReviewReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "threshold_review"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    rows_count: int
    recommendations_count: int

    recommendations: list[dict[str, Any]] = Field(default_factory=list)


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


def load_threshold_review_config() -> ThresholdReviewConfig:
    return ThresholdReviewConfig(
        output_dir=Path(os.getenv("THRESHOLD_REVIEW_OUTPUT_DIR", "artifacts/governance")),
        min_samples=env_int("THRESHOLD_REVIEW_MIN_SAMPLES", 20),
        min_win_rate=env_float("THRESHOLD_REVIEW_MIN_WIN_RATE", 0.52),
        min_avg_net_pnl_usd=env_float("THRESHOLD_REVIEW_MIN_AVG_NET_PNL_USD", 0.0),
        max_ece=env_float("THRESHOLD_REVIEW_MAX_ECE", 0.15),
        current_min_confidence={
            "5m": env_float("THRESHOLD_REVIEW_CURRENT_MIN_CONFIDENCE_5M", 0.65),
            "15m": env_float("THRESHOLD_REVIEW_CURRENT_MIN_CONFIDENCE_15M", 0.65),
            "1h": env_float("THRESHOLD_REVIEW_CURRENT_MIN_CONFIDENCE_1H", 0.65),
            "1D": env_float("THRESHOLD_REVIEW_CURRENT_MIN_CONFIDENCE_1D", 0.65),
        },
        current_min_edge={
            "5m": env_float("THRESHOLD_REVIEW_CURRENT_MIN_EDGE_5M", 0.03),
            "15m": env_float("THRESHOLD_REVIEW_CURRENT_MIN_EDGE_15M", 0.02),
            "1h": env_float("THRESHOLD_REVIEW_CURRENT_MIN_EDGE_1H", 0.015),
            "1D": env_float("THRESHOLD_REVIEW_CURRENT_MIN_EDGE_1D", 0.01),
        },
    )


def average(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None]

    if not clean:
        return None

    return sum(clean) / len(clean)


def build_timeframe_recommendation(
    *,
    timeframe: str,
    rows: list[LearningFeedbackRow],
    config: ThresholdReviewConfig,
) -> ThresholdRecommendation:
    trades = [row for row in rows if row.target is not None]
    wins = [row for row in trades if row.target == 1]

    samples = len(rows)
    trades_count = len(trades)

    win_rate = len(wins) / trades_count if trades_count else None
    avg_pnl = average([row.realized_net_pnl_usd for row in trades if row.realized_net_pnl_usd is not None])
    avg_confidence = average(
        [
            value
            for row in rows
            for value in [row.model_confidence or row.model_probability]
            if value is not None
        ]
    )
    avg_edge = average([row.expected_value_usd for row in rows if row.expected_value_usd is not None])

    current_conf = config.current_min_confidence.get(timeframe)
    current_edge = config.current_min_edge.get(timeframe)

    if samples < config.min_samples:
        return ThresholdRecommendation(
            timeframe=timeframe,
            action="COLLECT_MORE_DATA",
            reason="Amostra insuficiente para recomendar ajuste.",
            samples=samples,
            trades=trades_count,
            win_rate=win_rate,
            avg_net_pnl_usd=avg_pnl,
            avg_confidence=avg_confidence,
            avg_expected_value_usd=avg_edge,
            current_min_confidence=current_conf,
            recommended_min_confidence=current_conf,
            current_min_edge=current_edge,
            recommended_min_edge=current_edge,
        )

    if win_rate is not None and win_rate < config.min_win_rate:
        recommended = min(0.95, (current_conf or 0.65) + 0.05)

        return ThresholdRecommendation(
            timeframe=timeframe,
            action="INCREASE_MIN_CONFIDENCE",
            reason="Win rate abaixo do mínimo; recomenda-se exigir maior confiança.",
            samples=samples,
            trades=trades_count,
            win_rate=win_rate,
            avg_net_pnl_usd=avg_pnl,
            avg_confidence=avg_confidence,
            avg_expected_value_usd=avg_edge,
            current_min_confidence=current_conf,
            recommended_min_confidence=recommended,
            current_min_edge=current_edge,
            recommended_min_edge=current_edge,
        )

    if avg_pnl is not None and avg_pnl < config.min_avg_net_pnl_usd:
        recommended_edge = (current_edge or 0.0) + 0.005

        return ThresholdRecommendation(
            timeframe=timeframe,
            action="INCREASE_MIN_EDGE",
            reason="PnL médio abaixo do mínimo; recomenda-se aumentar edge mínimo.",
            samples=samples,
            trades=trades_count,
            win_rate=win_rate,
            avg_net_pnl_usd=avg_pnl,
            avg_confidence=avg_confidence,
            avg_expected_value_usd=avg_edge,
            current_min_confidence=current_conf,
            recommended_min_confidence=current_conf,
            current_min_edge=current_edge,
            recommended_min_edge=recommended_edge,
        )

    return ThresholdRecommendation(
        timeframe=timeframe,
        action="KEEP_THRESHOLDS",
        reason="Métricas dentro dos limites; manter thresholds por enquanto.",
        samples=samples,
        trades=trades_count,
        win_rate=win_rate,
        avg_net_pnl_usd=avg_pnl,
        avg_confidence=avg_confidence,
        avg_expected_value_usd=avg_edge,
        current_min_confidence=current_conf,
        recommended_min_confidence=current_conf,
        current_min_edge=current_edge,
        recommended_min_edge=current_edge,
    )


def build_threshold_review_report(
    *,
    rows: list[LearningFeedbackRow | dict[str, Any]],
    config: ThresholdReviewConfig | None = None,
) -> ThresholdReviewReport:
    resolved_config = config or load_threshold_review_config()
    parsed_rows = [
        row if isinstance(row, LearningFeedbackRow) else LearningFeedbackRow.model_validate(row)
        for row in rows
    ]

    grouped: dict[str, list[LearningFeedbackRow]] = defaultdict(list)

    for row in parsed_rows:
        grouped[row.timeframe or "unknown"].append(row)

    recommendations = [
        build_timeframe_recommendation(
            timeframe=timeframe,
            rows=timeframe_rows,
            config=resolved_config,
        )
        for timeframe, timeframe_rows in sorted(grouped.items())
    ]

    blocking_actions = {"PAUSE_TIMEFRAME", "REDUCE_EXPOSURE"}
    passed = not any(item.action in blocking_actions for item in recommendations)

    return ThresholdReviewReport(
        passed=passed,
        status="PASS" if passed else "WARN",
        rows_count=len(parsed_rows),
        recommendations_count=len(recommendations),
        recommendations=[item.model_dump(mode="json") for item in recommendations],
    )


def export_threshold_review_report(
    report: ThresholdReviewReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "threshold_review_latest",
) -> Path:
    config = load_threshold_review_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path