from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from data.learning_feedback_dataset import LearningFeedbackRow


load_dotenv()


DriftStatus = Literal["STABLE", "WATCH", "DRIFT"]


class LiveDriftConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live")

    min_samples: int = 20
    max_brier_score: float = 0.25
    max_ece: float = 0.15
    max_ood_rate: float = 0.20
    max_confidence_gap: float = 0.20
    min_win_rate_at_high_confidence: float = 0.52
    high_confidence_threshold: float = 0.65


class LiveDriftReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_drift_monitor"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: DriftStatus
    passed: bool

    samples_count: int
    labeled_samples_count: int

    brier_score: float | None = None
    expected_calibration_error: float | None = None
    ood_rate: float = 0.0
    average_confidence: float | None = None
    observed_win_rate: float | None = None
    confidence_gap: float | None = None
    high_confidence_win_rate: float | None = None

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    buckets: list[dict[str, Any]] = Field(default_factory=list)
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


def load_live_drift_config() -> LiveDriftConfig:
    return LiveDriftConfig(
        output_dir=Path(os.getenv("LIVE_DRIFT_OUTPUT_DIR", "artifacts/live")),
        min_samples=env_int("LIVE_DRIFT_MIN_SAMPLES", 20),
        max_brier_score=env_float("LIVE_DRIFT_MAX_BRIER_SCORE", 0.25),
        max_ece=env_float("LIVE_DRIFT_MAX_ECE", 0.15),
        max_ood_rate=env_float("LIVE_DRIFT_MAX_OOD_RATE", 0.20),
        max_confidence_gap=env_float("LIVE_DRIFT_MAX_CONFIDENCE_GAP", 0.20),
        min_win_rate_at_high_confidence=env_float("LIVE_DRIFT_MIN_WIN_RATE_AT_HIGH_CONFIDENCE", 0.52),
        high_confidence_threshold=env_float("LIVE_DRIFT_HIGH_CONFIDENCE_THRESHOLD", 0.65),
    )


def probability_from_row(row: LearningFeedbackRow) -> float | None:
    value = row.model_probability if row.model_probability is not None else row.model_confidence

    if value is None:
        return None

    return max(0.0, min(1.0, float(value)))


def calculate_brier_score(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None

    return sum((prob - target) ** 2 for prob, target in pairs) / len(pairs)


def calculate_ece(pairs: list[tuple[float, int]], *, buckets_count: int = 10) -> tuple[float | None, list[dict[str, Any]]]:
    if not pairs:
        return None, []

    buckets: list[dict[str, Any]] = []

    total = len(pairs)
    ece = 0.0

    for index in range(buckets_count):
        lower = index / buckets_count
        upper = (index + 1) / buckets_count

        if index == buckets_count - 1:
            bucket_pairs = [(p, y) for p, y in pairs if lower <= p <= upper]
        else:
            bucket_pairs = [(p, y) for p, y in pairs if lower <= p < upper]

        if not bucket_pairs:
            buckets.append(
                {
                    "bucket_index": index,
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "count": 0,
                    "average_probability": None,
                    "observed_frequency": None,
                    "absolute_gap": None,
                }
            )
            continue

        avg_prob = sum(p for p, _ in bucket_pairs) / len(bucket_pairs)
        observed = sum(y for _, y in bucket_pairs) / len(bucket_pairs)
        gap = abs(avg_prob - observed)
        ece += (len(bucket_pairs) / total) * gap

        buckets.append(
            {
                "bucket_index": index,
                "lower_bound": lower,
                "upper_bound": upper,
                "count": len(bucket_pairs),
                "average_probability": avg_prob,
                "observed_frequency": observed,
                "absolute_gap": gap,
            }
        )

    return ece, buckets


def build_live_drift_report(
    *,
    rows: list[LearningFeedbackRow | dict[str, Any]],
    config: LiveDriftConfig | None = None,
) -> LiveDriftReport:
    resolved_config = config or load_live_drift_config()

    parsed_rows = [
        row if isinstance(row, LearningFeedbackRow) else LearningFeedbackRow.model_validate(row)
        for row in rows
    ]

    labeled = [row for row in parsed_rows if row.target is not None]
    pairs: list[tuple[float, int]] = []

    for row in labeled:
        prob = probability_from_row(row)

        if prob is None:
            continue

        pairs.append((prob, int(row.target or 0)))

    brier = calculate_brier_score(pairs)
    ece, buckets = calculate_ece(pairs)

    ood_count = sum(1 for row in parsed_rows if row.ood_detected)
    ood_rate = ood_count / len(parsed_rows) if parsed_rows else 0.0

    avg_confidence = sum(prob for prob, _ in pairs) / len(pairs) if pairs else None
    observed_win_rate = sum(target for _, target in pairs) / len(pairs) if pairs else None

    confidence_gap = None
    if avg_confidence is not None and observed_win_rate is not None:
        confidence_gap = abs(avg_confidence - observed_win_rate)

    high_conf_pairs = [
        (prob, target)
        for prob, target in pairs
        if prob >= resolved_config.high_confidence_threshold
    ]

    high_conf_win_rate = (
        sum(target for _, target in high_conf_pairs) / len(high_conf_pairs)
        if high_conf_pairs
        else None
    )

    blockers: list[str] = []
    warnings: list[str] = []

    if len(pairs) < resolved_config.min_samples:
        warnings.append("labeled_samples_below_minimum")

    if brier is not None and brier > resolved_config.max_brier_score:
        blockers.append("brier_score_above_limit")

    if ece is not None and ece > resolved_config.max_ece:
        warnings.append("ece_above_limit")

    if ood_rate > resolved_config.max_ood_rate:
        blockers.append("ood_rate_above_limit")

    if confidence_gap is not None and confidence_gap > resolved_config.max_confidence_gap:
        warnings.append("confidence_gap_above_limit")

    if high_conf_win_rate is not None and high_conf_win_rate < resolved_config.min_win_rate_at_high_confidence:
        warnings.append("high_confidence_win_rate_below_minimum")

    passed = not blockers

    if blockers:
        status: DriftStatus = "DRIFT"
    elif warnings:
        status = "WATCH"
    else:
        status = "STABLE"

    return LiveDriftReport(
        status=status,
        passed=passed,
        samples_count=len(parsed_rows),
        labeled_samples_count=len(pairs),
        brier_score=round(brier, 8) if brier is not None else None,
        expected_calibration_error=round(ece, 8) if ece is not None else None,
        ood_rate=round(ood_rate, 8),
        average_confidence=round(avg_confidence, 8) if avg_confidence is not None else None,
        observed_win_rate=round(observed_win_rate, 8) if observed_win_rate is not None else None,
        confidence_gap=round(confidence_gap, 8) if confidence_gap is not None else None,
        high_confidence_win_rate=round(high_conf_win_rate, 8) if high_conf_win_rate is not None else None,
        blockers=blockers,
        warnings=warnings,
        buckets=buckets,
        config=resolved_config.model_dump(mode="json"),
    )


def export_live_drift_report(
    report: LiveDriftReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "live_drift_latest",
) -> Path:
    config = load_live_drift_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path