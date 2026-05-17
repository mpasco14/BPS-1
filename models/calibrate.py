"""
Probability calibration.

Responsabilidades:
- Calibrar probabilidades previstas por modelos.
- Suportar Platt Scaling.
- Suportar Isotonic Regression simples via PAVA.
- Salvar/carregar calibrador em JSON.

Este módulo NÃO treina o modelo principal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

import numpy as np
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


CalibrationMethod = Literal["platt", "isotonic"]


class CalibrationArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    method: CalibrationMethod
    params: dict
    train_brier_score: float | None = None
    metadata: dict = Field(default_factory=dict)


def clip_probs(values: np.ndarray) -> np.ndarray:
    return np.clip(values.astype(float), 1e-6, 1 - 1e-6)


def logit(probabilities: np.ndarray) -> np.ndarray:
    probs = clip_probs(probabilities)

    return np.log(probs / (1 - probs))


def sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, -50, 50)

    return 1 / (1 + np.exp(-values))


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0

    return float(np.mean((y_prob - y_true) ** 2))


def fit_platt_calibrator(
    *,
    y_true: np.ndarray,
    y_prob: np.ndarray,
    learning_rate: float = 0.05,
    epochs: int = 1000,
    l2: float = 0.001,
) -> CalibrationArtifact:
    if len(y_true) == 0:
        raise ValueError("dataset vazio para calibração")

    x = logit(y_prob)
    y = y_true.astype(float)

    a = 1.0
    b = 0.0

    for _ in range(epochs):
        pred = sigmoid(a * x + b)
        error = pred - y

        grad_a = float(np.mean(error * x)) + l2 * a
        grad_b = float(np.mean(error))

        a -= learning_rate * grad_a
        b -= learning_rate * grad_b

    calibrated = sigmoid(a * x + b)

    return CalibrationArtifact(
        method="platt",
        params={"a": a, "b": b},
        train_brier_score=brier_score(y, calibrated),
    )


def apply_platt(
    artifact: CalibrationArtifact,
    probabilities: np.ndarray,
) -> np.ndarray:
    a = float(artifact.params["a"])
    b = float(artifact.params["b"])

    return sigmoid(a * logit(probabilities) + b)


def fit_isotonic_calibrator(
    *,
    y_true: np.ndarray,
    y_prob: np.ndarray,
) -> CalibrationArtifact:
    if len(y_true) == 0:
        raise ValueError("dataset vazio para calibração")

    order = np.argsort(y_prob)
    x_sorted = y_prob[order].astype(float)
    y_sorted = y_true[order].astype(float)

    blocks: list[dict] = []

    for x, y in zip(x_sorted, y_sorted):
        blocks.append(
            {
                "x_min": x,
                "x_max": x,
                "sum_y": y,
                "count": 1,
                "value": y,
            }
        )

        while len(blocks) >= 2 and blocks[-2]["value"] > blocks[-1]["value"]:
            right = blocks.pop()
            left = blocks.pop()

            merged = {
                "x_min": left["x_min"],
                "x_max": right["x_max"],
                "sum_y": left["sum_y"] + right["sum_y"],
                "count": left["count"] + right["count"],
            }
            merged["value"] = merged["sum_y"] / merged["count"]

            blocks.append(merged)

    thresholds = [float(block["x_max"]) for block in blocks]
    values = [float(block["value"]) for block in blocks]

    artifact = CalibrationArtifact(
        method="isotonic",
        params={
            "thresholds": thresholds,
            "values": values,
        },
    )

    artifact.train_brier_score = brier_score(
        y_true.astype(float),
        apply_isotonic(artifact, y_prob),
    )

    return artifact


def apply_isotonic(
    artifact: CalibrationArtifact,
    probabilities: np.ndarray,
) -> np.ndarray:
    thresholds = np.array(artifact.params["thresholds"], dtype=float)
    values = np.array(artifact.params["values"], dtype=float)

    if len(thresholds) == 0:
        return probabilities

    output = []

    for prob in probabilities:
        index = np.searchsorted(thresholds, prob, side="left")
        index = min(index, len(values) - 1)

        output.append(values[index])

    return np.array(output, dtype=float)


def fit_calibrator(
    *,
    y_true: np.ndarray,
    y_prob: np.ndarray,
    method: str | None = None,
) -> CalibrationArtifact:
    selected = (method or os.getenv("CALIBRATION_METHOD", "platt")).strip().lower()

    if selected == "platt":
        return fit_platt_calibrator(
            y_true=y_true,
            y_prob=y_prob,
        )

    if selected == "isotonic":
        return fit_isotonic_calibrator(
            y_true=y_true,
            y_prob=y_prob,
        )

    raise ValueError(f"método de calibração não suportado: {selected}")


def apply_calibration(
    artifact: CalibrationArtifact,
    probabilities: np.ndarray,
) -> np.ndarray:
    if artifact.method == "platt":
        return apply_platt(artifact, probabilities)

    if artifact.method == "isotonic":
        return apply_isotonic(artifact, probabilities)

    raise ValueError(f"método não suportado: {artifact.method}")


def save_calibrator(
    artifact: CalibrationArtifact,
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def load_calibrator(path: str | Path) -> CalibrationArtifact:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    return CalibrationArtifact.model_validate(payload)