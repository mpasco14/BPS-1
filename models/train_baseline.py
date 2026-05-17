"""
Baseline logistic regression model.

Responsabilidades:
- Treinar baseline simples para prever target TP antes de SL.
- Usar apenas numpy para evitar dependências pesadas nesta etapa.
- Calcular log_loss, Brier score e accuracy.
- Servir como benchmark mínimo para modelos futuros como LightGBM.

Este módulo NÃO executa trades.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from data.historical_dataset import DatasetRow


load_dotenv()


DEFAULT_FEATURE_COLUMNS = [
    "tech_score",
    "microstructure_score",
    "onchain_score",
    "sentiment_score",
    "combined_score",
    "binance_spread_pct",
    "binance_liquidity_usd",
    "funding_rate",
    "open_interest",
    "mark_price",
]


class BaselineMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    samples: int
    log_loss: float
    brier_score: float
    accuracy: float


class BaselineModelArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    model_name: str
    feature_columns: list[str]

    weights: list[float]
    bias: float

    train_metrics: dict[str, Any]
    validation_metrics: dict[str, Any] | None = None
    test_metrics: dict[str, Any] | None = None

    feature_means: list[float]
    feature_stds: list[float]


def parse_feature_columns(value: str | None = None) -> list[str]:
    raw = value or os.getenv("BASELINE_MODEL_FEATURES")

    if not raw:
        return DEFAULT_FEATURE_COLUMNS

    return [item.strip() for item in raw.split(",") if item.strip()]


def safe_float(value: Any) -> float:
    if value is None:
        return 0.0

    try:
        parsed = float(value)

        if math.isnan(parsed) or math.isinf(parsed):
            return 0.0

        return parsed
    except (TypeError, ValueError):
        return 0.0


def rows_to_matrix(
    rows: list[DatasetRow],
    *,
    feature_columns: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    filtered = [row for row in rows if row.target in {0, 1}]

    x_values: list[list[float]] = []
    y_values: list[int] = []

    for row in filtered:
        payload = row.model_dump(mode="python")

        x_values.append([safe_float(payload.get(column)) for column in feature_columns])
        y_values.append(int(row.target))

    if not x_values:
        return np.empty((0, len(feature_columns))), np.empty((0,))

    return np.array(x_values, dtype=float), np.array(y_values, dtype=float)


def standardize_train(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if x.size == 0:
        means = np.zeros((x.shape[1],))
        stds = np.ones((x.shape[1],))
        return x, means, stds

    means = x.mean(axis=0)
    stds = x.std(axis=0)
    stds = np.where(stds == 0, 1.0, stds)

    return (x - means) / stds, means, stds


def standardize_apply(x: np.ndarray, means: np.ndarray, stds: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x

    return (x - means) / stds


def sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, -50, 50)

    return 1 / (1 + np.exp(-values))


def log_loss(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0

    eps = 1e-12
    probs = np.clip(y_prob, eps, 1 - eps)

    return float(-np.mean(y_true * np.log(probs) + (1 - y_true) * np.log(1 - probs)))


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0

    return float(np.mean((y_prob - y_true) ** 2))


def accuracy_score(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5) -> float:
    if len(y_true) == 0:
        return 0.0

    predictions = (y_prob >= threshold).astype(float)

    return float(np.mean(predictions == y_true))


class LogisticRegressionBaseline:
    def __init__(
        self,
        *,
        learning_rate: float = 0.05,
        epochs: int = 1000,
        l2: float = 0.001,
    ) -> None:
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.l2 = l2
        self.weights: np.ndarray | None = None
        self.bias: float = 0.0

    def fit(self, x: np.ndarray, y: np.ndarray) -> "LogisticRegressionBaseline":
        if len(y) == 0:
            raise ValueError("dataset vazio para treinamento")

        n_samples, n_features = x.shape

        self.weights = np.zeros(n_features, dtype=float)
        self.bias = 0.0

        for _ in range(self.epochs):
            logits = x @ self.weights + self.bias
            probs = sigmoid(logits)

            error = probs - y

            grad_w = (x.T @ error) / n_samples + self.l2 * self.weights
            grad_b = float(np.mean(error))

            self.weights -= self.learning_rate * grad_w
            self.bias -= self.learning_rate * grad_b

        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self.weights is None:
            raise ValueError("modelo ainda não foi treinado")

        return sigmoid(x @ self.weights + self.bias)


def evaluate_model(
    *,
    model: LogisticRegressionBaseline,
    x: np.ndarray,
    y: np.ndarray,
) -> BaselineMetrics:
    if len(y) == 0:
        return BaselineMetrics(
            samples=0,
            log_loss=0.0,
            brier_score=0.0,
            accuracy=0.0,
        )

    probs = model.predict_proba(x)

    return BaselineMetrics(
        samples=len(y),
        log_loss=log_loss(y, probs),
        brier_score=brier_score(y, probs),
        accuracy=accuracy_score(y, probs),
    )


def train_baseline_model(
    *,
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow] | None = None,
    test_rows: list[DatasetRow] | None = None,
    feature_columns: list[str] | None = None,
    learning_rate: float | None = None,
    epochs: int | None = None,
    l2: float | None = None,
) -> BaselineModelArtifact:
    columns = feature_columns or parse_feature_columns()

    x_train_raw, y_train = rows_to_matrix(train_rows, feature_columns=columns)
    x_train, means, stds = standardize_train(x_train_raw)

    model = LogisticRegressionBaseline(
        learning_rate=learning_rate if learning_rate is not None else float(os.getenv("BASELINE_MODEL_LEARNING_RATE", "0.05")),
        epochs=epochs if epochs is not None else int(os.getenv("BASELINE_MODEL_EPOCHS", "1000")),
        l2=l2 if l2 is not None else float(os.getenv("BASELINE_MODEL_L2", "0.001")),
    )

    model.fit(x_train, y_train)

    train_metrics = evaluate_model(model=model, x=x_train, y=y_train)

    validation_metrics = None

    if validation_rows is not None:
        x_val_raw, y_val = rows_to_matrix(validation_rows, feature_columns=columns)
        x_val = standardize_apply(x_val_raw, means, stds)
        validation_metrics = evaluate_model(model=model, x=x_val, y=y_val)

    test_metrics = None

    if test_rows is not None:
        x_test_raw, y_test = rows_to_matrix(test_rows, feature_columns=columns)
        x_test = standardize_apply(x_test_raw, means, stds)
        test_metrics = evaluate_model(model=model, x=x_test, y=y_test)

    assert model.weights is not None

    return BaselineModelArtifact(
        model_name=os.getenv("BASELINE_MODEL_NAME", "btc_binance_futures_logistic_baseline"),
        feature_columns=columns,
        weights=model.weights.tolist(),
        bias=model.bias,
        train_metrics=train_metrics.model_dump(mode="json"),
        validation_metrics=validation_metrics.model_dump(mode="json") if validation_metrics else None,
        test_metrics=test_metrics.model_dump(mode="json") if test_metrics else None,
        feature_means=means.tolist(),
        feature_stds=stds.tolist(),
    )


def save_model_artifact(artifact: BaselineModelArtifact, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def load_model_artifact(path: str | Path) -> BaselineModelArtifact:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    return BaselineModelArtifact.model_validate(payload)