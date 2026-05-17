"""
Realtime prediction interface.

Responsabilidades:
- Carregar artefatos baseline ou LightGBM.
- Aplicar calibrador opcional.
- Calcular expected value.
- Fazer OOD detection simples por z-score.
- Retornar decisão auditável.

Este módulo NÃO executa ordens.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import numpy as np
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from models.calibrate import CalibrationArtifact, apply_calibration, load_calibrator
from models.model_registry import ModelRegistryRecord, load_latest_record, load_registry_record
from models.train_baseline import BaselineModelArtifact, load_model_artifact, safe_float, sigmoid


load_dotenv()


PredictionDecision = Literal["candidate_trade", "reject", "hold"]


class PredictionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "predict"
    model_name: str
    model_version: str
    model_type: str

    side: str

    prob_tp: float
    calibrated_prob_tp: float | None = None

    expected_value_usd: float
    decision: PredictionDecision

    confidence: float

    ood_status: str = "not_checked"
    ood_reasons: list[str] = Field(default_factory=list)

    reasons: list[str] = Field(default_factory=list)


def row_from_features(
    features: dict[str, Any],
    feature_columns: list[str],
) -> np.ndarray:
    return np.array(
        [[safe_float(features.get(column)) for column in feature_columns]],
        dtype=float,
    )


def expected_value_usd(
    *,
    prob_win: float,
    gross_take_profit_usd: float | None = None,
    gross_stop_loss_usd: float | None = None,
    estimated_fees_usd: float | None = None,
) -> float:
    profit = (
        gross_take_profit_usd
        if gross_take_profit_usd is not None
        else float(os.getenv("PREDICT_GROSS_TAKE_PROFIT_USD", "2.10"))
    )

    loss = (
        gross_stop_loss_usd
        if gross_stop_loss_usd is not None
        else float(os.getenv("PREDICT_GROSS_STOP_LOSS_USD", "1.05"))
    )

    fees = (
        estimated_fees_usd
        if estimated_fees_usd is not None
        else float(os.getenv("PREDICT_ESTIMATED_FEES_USD", "0.10"))
    )

    return prob_win * profit - (1 - prob_win) * loss - fees


def detect_ood(
    *,
    features: dict[str, Any],
    feature_columns: list[str],
    means: list[float] | None = None,
    stds: list[float] | None = None,
    max_zscore: float | None = None,
) -> tuple[str, list[str]]:
    if not means or not stds:
        return "not_checked", []

    limit = max_zscore if max_zscore is not None else float(os.getenv("PREDICT_OOD_MAX_ZSCORE", "4.0"))

    reasons: list[str] = []

    for column, mean, std in zip(feature_columns, means, stds):
        value = safe_float(features.get(column))
        std_value = std if std != 0 else 1.0

        zscore = abs((value - mean) / std_value)

        if zscore > limit:
            reasons.append(f"ood_{column}_zscore:{zscore:.4f}")

    if reasons:
        return "out_of_distribution", reasons

    return "in_distribution", []


def predict_baseline_artifact(
    *,
    artifact: BaselineModelArtifact,
    features: dict[str, Any],
    side: str,
    calibrator: CalibrationArtifact | None = None,
) -> PredictionResult:
    x = row_from_features(features, artifact.feature_columns)

    means = np.array(artifact.feature_means, dtype=float)
    stds = np.array(artifact.feature_stds, dtype=float)
    stds = np.where(stds == 0, 1.0, stds)

    x_scaled = (x - means) / stds

    weights = np.array(artifact.weights, dtype=float)
    bias = float(artifact.bias)

    prob = float(sigmoid(x_scaled @ weights + bias)[0])
    calibrated = None

    if calibrator is not None:
        calibrated = float(apply_calibration(calibrator, np.array([prob]))[0])

    final_prob = calibrated if calibrated is not None else prob
    ev = expected_value_usd(prob_win=final_prob)

    min_ev = float(os.getenv("PREDICT_MIN_EXPECTED_VALUE_USD", "0.15"))

    ood_status, ood_reasons = detect_ood(
        features=features,
        feature_columns=artifact.feature_columns,
        means=artifact.feature_means,
        stds=artifact.feature_stds,
    )

    reject_on_ood = os.getenv("PREDICT_REJECT_ON_OOD", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    reasons = [
        f"expected_value_usd:{ev:.6f}",
        f"prob_tp:{final_prob:.6f}",
    ]

    if reject_on_ood and ood_status == "out_of_distribution":
        decision: PredictionDecision = "reject"
        reasons.append("rejected_by_ood")
    elif ev >= min_ev:
        decision = "candidate_trade"
        reasons.append("positive_expected_value")
    else:
        decision = "hold"
        reasons.append("expected_value_below_minimum")

    return PredictionResult(
        model_name=artifact.model_name,
        model_version="baseline_artifact",
        model_type="baseline_logistic",
        side=side,
        prob_tp=prob,
        calibrated_prob_tp=calibrated,
        expected_value_usd=ev,
        decision=decision,
        confidence=abs(final_prob - 0.5) * 2,
        ood_status=ood_status,
        ood_reasons=ood_reasons,
        reasons=reasons,
    )


def import_lightgbm():
    try:
        import lightgbm as lgb  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "lightgbm não está instalado. Instale com: pip install lightgbm"
        ) from exc

    return lgb


def predict_lightgbm_record(
    *,
    record: ModelRegistryRecord,
    features: dict[str, Any],
    side: str,
    calibrator: CalibrationArtifact | None = None,
) -> PredictionResult:
    if not record.model_path:
        raise ValueError("registry record sem model_path")

    lgb = import_lightgbm()
    booster = lgb.Booster(model_file=record.model_path)

    x = row_from_features(features, record.feature_columns)
    raw_prediction = booster.predict(x)

    prob = float(raw_prediction[0])
    calibrated = None

    if calibrator is not None:
        calibrated = float(apply_calibration(calibrator, np.array([prob]))[0])

    final_prob = calibrated if calibrated is not None else prob
    ev = expected_value_usd(prob_win=final_prob)
    min_ev = float(os.getenv("PREDICT_MIN_EXPECTED_VALUE_USD", "0.15"))

    decision: PredictionDecision = "candidate_trade" if ev >= min_ev else "hold"

    return PredictionResult(
        model_name=record.model_name,
        model_version=record.model_version,
        model_type=record.model_type,
        side=side,
        prob_tp=prob,
        calibrated_prob_tp=calibrated,
        expected_value_usd=ev,
        decision=decision,
        confidence=abs(final_prob - 0.5) * 2,
        ood_status="not_checked",
        reasons=[
            f"expected_value_usd:{ev:.6f}",
            f"prob_tp:{final_prob:.6f}",
        ],
    )


def load_optional_calibrator(path: str | None) -> CalibrationArtifact | None:
    if not path:
        return None

    if not Path(path).exists():
        return None

    return load_calibrator(path)


def predict(
    *,
    features: dict[str, Any],
    side: str,
    artifact_path: str | None = None,
    registry_record_path: str | None = None,
    model_name: str | None = None,
    calibrator_path: str | None = None,
) -> PredictionResult:
    calibrator = load_optional_calibrator(calibrator_path)

    if artifact_path:
        artifact = load_model_artifact(artifact_path)

        return predict_baseline_artifact(
            artifact=artifact,
            features=features,
            side=side,
            calibrator=calibrator,
        )

    if registry_record_path:
        record = load_registry_record(registry_record_path)

        return predict_lightgbm_record(
            record=record,
            features=features,
            side=side,
            calibrator=calibrator,
        )

    if model_name:
        record = load_latest_record(model_name)

        return predict_lightgbm_record(
            record=record,
            features=features,
            side=side,
            calibrator=calibrator,
        )

    raise ValueError("forneça artifact_path, registry_record_path ou model_name")


def prediction_to_dict(result: PredictionResult) -> dict[str, Any]:
    return result.model_dump(mode="json")