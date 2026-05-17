"""
LightGBM training module.

Responsabilidades:
- Treinar modelo LightGBM para prever TP antes de SL.
- Avaliar log_loss, Brier score e accuracy.
- Salvar modelo e metadados.
- Registrar modelo no model_registry.

Este módulo NÃO executa trades.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from data.historical_dataset import DatasetRow
from models.model_registry import register_model, utc_version
from models.train_baseline import (
    BaselineMetrics,
    accuracy_score,
    brier_score,
    log_loss,
    parse_feature_columns,
    rows_to_matrix,
)


load_dotenv()


class LightGBMTrainingResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    model_name: str
    model_version: str
    feature_columns: list[str]

    model_path: str
    metadata_path: str

    train_metrics: dict[str, Any]
    validation_metrics: dict[str, Any] | None = None
    test_metrics: dict[str, Any] | None = None

    registry_record: dict[str, Any] | None = None


def import_lightgbm():
    try:
        import lightgbm as lgb  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "lightgbm não está instalado. Instale com: pip install lightgbm"
        ) from exc

    return lgb


def lightgbm_available() -> bool:
    try:
        import_lightgbm()
        return True
    except RuntimeError:
        return False


def default_params() -> dict[str, Any]:
    return {
        "objective": os.getenv("LIGHTGBM_OBJECTIVE", "binary"),
        "n_estimators": int(os.getenv("LIGHTGBM_N_ESTIMATORS", "200")),
        "learning_rate": float(os.getenv("LIGHTGBM_LEARNING_RATE", "0.05")),
        "max_depth": int(os.getenv("LIGHTGBM_MAX_DEPTH", "-1")),
        "num_leaves": int(os.getenv("LIGHTGBM_NUM_LEAVES", "31")),
        "min_child_samples": int(os.getenv("LIGHTGBM_MIN_CHILD_SAMPLES", "20")),
        "subsample": float(os.getenv("LIGHTGBM_SUBSAMPLE", "0.9")),
        "colsample_bytree": float(os.getenv("LIGHTGBM_COLSAMPLE_BYTREE", "0.9")),
        "reg_alpha": float(os.getenv("LIGHTGBM_REG_ALPHA", "0.0")),
        "reg_lambda": float(os.getenv("LIGHTGBM_REG_LAMBDA", "0.0")),
        "random_state": 42,
        "n_jobs": -1,
        "verbosity": -1,
    }


def evaluate_probabilities(
    y_true: np.ndarray,
    y_prob: np.ndarray,
) -> BaselineMetrics:
    return BaselineMetrics(
        samples=len(y_true),
        log_loss=log_loss(y_true, y_prob),
        brier_score=brier_score(y_true, y_prob),
        accuracy=accuracy_score(y_true, y_prob),
    )


def predict_positive_probability(model: Any, x: np.ndarray) -> np.ndarray:
    probabilities = model.predict_proba(x)

    if probabilities.ndim == 2:
        return probabilities[:, 1]

    return probabilities


def train_lightgbm_model(
    *,
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow] | None = None,
    test_rows: list[DatasetRow] | None = None,
    feature_columns: list[str] | None = None,
    params: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
    register: bool = True,
) -> LightGBMTrainingResult:
    lgb = import_lightgbm()

    columns = feature_columns or parse_feature_columns()
    x_train, y_train = rows_to_matrix(train_rows, feature_columns=columns)

    if len(y_train) == 0:
        raise ValueError("dataset vazio para LightGBM")

    model_params = default_params()

    if params:
        model_params.update(params)

    model = lgb.LGBMClassifier(**model_params)
    model.fit(x_train, y_train)

    train_probs = predict_positive_probability(model, x_train)
    train_metrics = evaluate_probabilities(y_train, train_probs)

    validation_metrics = None

    if validation_rows is not None:
        x_val, y_val = rows_to_matrix(validation_rows, feature_columns=columns)

        if len(y_val) > 0:
            validation_metrics = evaluate_probabilities(
                y_val,
                predict_positive_probability(model, x_val),
            )

    test_metrics = None

    if test_rows is not None:
        x_test, y_test = rows_to_matrix(test_rows, feature_columns=columns)

        if len(y_test) > 0:
            test_metrics = evaluate_probabilities(
                y_test,
                predict_positive_probability(model, x_test),
            )

    model_name = os.getenv("LIGHTGBM_MODEL_NAME", "btc_binance_futures_lgbm")
    model_version = utc_version("lgbm")

    resolved_output_dir = Path(
        output_dir or os.getenv("LIGHTGBM_MODEL_OUTPUT_DIR", "artifacts/models/lightgbm")
    )
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    model_path = resolved_output_dir / f"{model_name}_{model_version}.txt"
    metadata_path = resolved_output_dir / f"{model_name}_{model_version}.json"

    model.booster_.save_model(str(model_path))

    metadata = {
        "model_name": model_name,
        "model_version": model_version,
        "model_type": "lightgbm",
        "feature_columns": columns,
        "params": model_params,
        "train_metrics": train_metrics.model_dump(mode="json"),
        "validation_metrics": validation_metrics.model_dump(mode="json") if validation_metrics else None,
        "test_metrics": test_metrics.model_dump(mode="json") if test_metrics else None,
        "model_path": str(model_path),
    }

    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    registry_record = None

    if register:
        record = register_model(
            model_name=model_name,
            model_version=model_version,
            model_type="lightgbm",
            feature_columns=columns,
            model_path=str(model_path),
            metrics={
                "train": train_metrics.model_dump(mode="json"),
                "validation": validation_metrics.model_dump(mode="json") if validation_metrics else None,
                "test": test_metrics.model_dump(mode="json") if test_metrics else None,
            },
            metadata=metadata,
        )
        registry_record = record.model_dump(mode="json")

    return LightGBMTrainingResult(
        model_name=model_name,
        model_version=model_version,
        feature_columns=columns,
        model_path=str(model_path),
        metadata_path=str(metadata_path),
        train_metrics=train_metrics.model_dump(mode="json"),
        validation_metrics=validation_metrics.model_dump(mode="json") if validation_metrics else None,
        test_metrics=test_metrics.model_dump(mode="json") if test_metrics else None,
        registry_record=registry_record,
    )