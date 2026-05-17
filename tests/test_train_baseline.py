from pathlib import Path

import numpy as np

from data.historical_dataset import DatasetRow
from models.train_baseline import (
    LogisticRegressionBaseline,
    brier_score,
    log_loss,
    load_model_artifact,
    rows_to_matrix,
    save_model_artifact,
    sigmoid,
    train_baseline_model,
)


def make_row(index: int, target: int):
    score = 0.8 if target == 1 else -0.8

    return DatasetRow(
        timestamp=f"2026-05-15T18:{index:02d}:00+00:00",
        venue="binance_futures",
        symbol="BTCUSDT",
        timeframe="5m",
        side="LONG",
        target=target,
        outcome="take_profit" if target == 1 else "stop_loss",
        tech_score=score,
        microstructure_score=score,
        onchain_score=0.05 * score,
        sentiment_score=0.03 * score,
        combined_score=score,
        binance_spread_pct=0.0001,
        binance_liquidity_usd=100000,
        funding_rate=0.0001,
        open_interest=100000,
        mark_price=60000 + index,
    )


def test_sigmoid_bounds():
    values = sigmoid(np.array([-100, 0, 100]))

    assert values[0] >= 0
    assert values[1] == 0.5
    assert values[2] <= 1


def test_log_loss_and_brier_score():
    y = np.array([1, 0])
    p = np.array([0.9, 0.1])

    assert log_loss(y, p) > 0
    assert brier_score(y, p) < 0.05


def test_rows_to_matrix():
    rows = [make_row(0, 1), make_row(1, 0)]

    x, y = rows_to_matrix(
        rows,
        feature_columns=["tech_score", "combined_score"],
    )

    assert x.shape == (2, 2)
    assert y.tolist() == [1, 0]


def test_logistic_regression_baseline_fit_predict():
    x = np.array([[1.0], [-1.0], [0.8], [-0.8]])
    y = np.array([1, 0, 1, 0], dtype=float)

    model = LogisticRegressionBaseline(
        learning_rate=0.1,
        epochs=200,
        l2=0.0,
    )

    model.fit(x, y)
    probs = model.predict_proba(x)

    assert probs[0] > 0.5
    assert probs[1] < 0.5


def test_train_baseline_model():
    rows = [make_row(index, index % 2) for index in range(20)]

    artifact = train_baseline_model(
        train_rows=rows[:14],
        validation_rows=rows[14:17],
        test_rows=rows[17:],
        feature_columns=["tech_score", "combined_score"],
        learning_rate=0.1,
        epochs=300,
        l2=0.0,
    )

    assert artifact.model_name
    assert artifact.feature_columns == ["tech_score", "combined_score"]
    assert len(artifact.weights) == 2
    assert artifact.train_metrics["samples"] == 14
    assert artifact.validation_metrics["samples"] == 3
    assert artifact.test_metrics["samples"] == 3


def test_save_and_load_model_artifact(tmp_path: Path):
    rows = [make_row(index, index % 2) for index in range(10)]

    artifact = train_baseline_model(
        train_rows=rows,
        feature_columns=["tech_score", "combined_score"],
        learning_rate=0.1,
        epochs=100,
        l2=0.0,
    )

    path = save_model_artifact(artifact, tmp_path / "baseline.json")
    loaded = load_model_artifact(path)

    assert loaded.model_name == artifact.model_name
    assert loaded.feature_columns == artifact.feature_columns