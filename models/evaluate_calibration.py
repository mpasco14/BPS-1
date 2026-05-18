"""
Model calibration evaluation.

Responsabilidades:
- Calcular Brier Score.
- Calcular Expected Calibration Error.
- Construir calibration buckets.
- Exportar relatório JSON.
- Gerar curva de calibração opcional.

Este módulo NÃO treina modelo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


class CalibrationBucket(BaseModel):
    model_config = ConfigDict(extra="allow")

    bucket_index: int
    lower_bound: float
    upper_bound: float

    count: int
    average_probability: float | None
    observed_frequency: float | None
    absolute_gap: float | None


class CalibrationEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "calibration_evaluation"

    samples: int
    buckets_count: int

    brier_score: float
    expected_calibration_error: float

    buckets: list[dict[str, Any]] = Field(default_factory=list)


def validate_arrays(
    y_true: list[int | float] | np.ndarray,
    y_prob: list[float] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_prob, dtype=float)

    if len(y) != len(p):
        raise ValueError("y_true e y_prob precisam ter o mesmo tamanho.")

    if len(y) == 0:
        raise ValueError("dataset vazio para avaliação de calibração.")

    p = np.clip(p, 0.0, 1.0)

    return y, p


def brier_score_metric(
    y_true: list[int | float] | np.ndarray,
    y_prob: list[float] | np.ndarray,
) -> float:
    y, p = validate_arrays(y_true, y_prob)

    return float(np.mean((p - y) ** 2))


def build_calibration_buckets(
    y_true: list[int | float] | np.ndarray,
    y_prob: list[float] | np.ndarray,
    *,
    n_bins: int = 10,
) -> list[CalibrationBucket]:
    y, p = validate_arrays(y_true, y_prob)

    if n_bins <= 0:
        raise ValueError("n_bins precisa ser maior que zero.")

    buckets: list[CalibrationBucket] = []

    for index in range(n_bins):
        lower = index / n_bins
        upper = (index + 1) / n_bins

        if index == n_bins - 1:
            mask = (p >= lower) & (p <= upper)
        else:
            mask = (p >= lower) & (p < upper)

        count = int(np.sum(mask))

        if count == 0:
            buckets.append(
                CalibrationBucket(
                    bucket_index=index,
                    lower_bound=lower,
                    upper_bound=upper,
                    count=0,
                    average_probability=None,
                    observed_frequency=None,
                    absolute_gap=None,
                )
            )
            continue

        bucket_probs = p[mask]
        bucket_true = y[mask]

        average_probability = float(np.mean(bucket_probs))
        observed_frequency = float(np.mean(bucket_true))
        absolute_gap = abs(average_probability - observed_frequency)

        buckets.append(
            CalibrationBucket(
                bucket_index=index,
                lower_bound=lower,
                upper_bound=upper,
                count=count,
                average_probability=average_probability,
                observed_frequency=observed_frequency,
                absolute_gap=absolute_gap,
            )
        )

    return buckets


def expected_calibration_error(
    y_true: list[int | float] | np.ndarray,
    y_prob: list[float] | np.ndarray,
    *,
    n_bins: int = 10,
) -> float:
    y, _ = validate_arrays(y_true, y_prob)
    buckets = build_calibration_buckets(y_true, y_prob, n_bins=n_bins)

    total = len(y)
    ece = 0.0

    for bucket in buckets:
        if bucket.count == 0 or bucket.absolute_gap is None:
            continue

        ece += (bucket.count / total) * bucket.absolute_gap

    return float(ece)


def evaluate_probability_calibration(
    *,
    y_true: list[int | float] | np.ndarray,
    y_prob: list[float] | np.ndarray,
    n_bins: int | None = None,
) -> CalibrationEvaluationReport:
    selected_bins = n_bins or int(os.getenv("CALIBRATION_EVAL_BUCKETS", "10"))
    y, p = validate_arrays(y_true, y_prob)

    buckets = build_calibration_buckets(y, p, n_bins=selected_bins)

    return CalibrationEvaluationReport(
        samples=len(y),
        buckets_count=selected_bins,
        brier_score=brier_score_metric(y, p),
        expected_calibration_error=expected_calibration_error(y, p, n_bins=selected_bins),
        buckets=[bucket.model_dump(mode="json") for bucket in buckets],
    )


def export_calibration_report(
    report: CalibrationEvaluationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "calibration_report",
) -> Path:
    resolved_output_dir = Path(output_dir or os.getenv("CALIBRATION_EVAL_OUTPUT_DIR", "artifacts/model_evaluation"))
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path


def plot_calibration_curve(
    report: CalibrationEvaluationReport,
    *,
    output_path: str | Path,
) -> Path:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib não está instalado.") from exc

    probabilities = []
    frequencies = []

    for bucket in report.buckets:
        avg_prob = bucket.get("average_probability")
        observed = bucket.get("observed_frequency")

        if avg_prob is None or observed is None:
            continue

        probabilities.append(avg_prob)
        frequencies.append(observed)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    plt.figure()
    plt.plot([0, 1], [0, 1], linestyle="--")
    plt.plot(probabilities, frequencies, marker="o")
    plt.xlabel("Probabilidade prevista")
    plt.ylabel("Frequência real")
    plt.title("Calibration Curve")
    plt.savefig(path)
    plt.close()

    return path


def calibration_report_to_dict(report: CalibrationEvaluationReport) -> dict[str, Any]:
    return report.model_dump(mode="json")