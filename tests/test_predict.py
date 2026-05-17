from models.predict import (
    detect_ood,
    expected_value_usd,
    predict_baseline_artifact,
)
from models.train_baseline import BaselineModelArtifact


def sample_artifact():
    return BaselineModelArtifact(
        model_name="baseline",
        feature_columns=["combined_score", "tech_score"],
        weights=[2.0, 1.0],
        bias=0.0,
        train_metrics={"samples": 10},
        feature_means=[0.0, 0.0],
        feature_stds=[1.0, 1.0],
    )


def test_expected_value_positive():
    ev = expected_value_usd(
        prob_win=0.6,
        gross_take_profit_usd=2.10,
        gross_stop_loss_usd=1.05,
        estimated_fees_usd=0.10,
    )

    assert ev > 0


def test_detect_ood_in_distribution():
    status, reasons = detect_ood(
        features={"a": 0.1},
        feature_columns=["a"],
        means=[0.0],
        stds=[1.0],
        max_zscore=4.0,
    )

    assert status == "in_distribution"
    assert reasons == []


def test_detect_ood_out_of_distribution():
    status, reasons = detect_ood(
        features={"a": 10.0},
        feature_columns=["a"],
        means=[0.0],
        stds=[1.0],
        max_zscore=4.0,
    )

    assert status == "out_of_distribution"
    assert reasons


def test_predict_baseline_artifact_candidate_trade():
    result = predict_baseline_artifact(
        artifact=sample_artifact(),
        features={"combined_score": 1.0, "tech_score": 1.0},
        side="LONG",
    )

    assert result.prob_tp > 0.5
    assert result.expected_value_usd > 0
    assert result.decision in {"candidate_trade", "hold"}


def test_predict_baseline_artifact_hold():
    result = predict_baseline_artifact(
        artifact=sample_artifact(),
        features={"combined_score": -1.0, "tech_score": -1.0},
        side="LONG",
    )

    assert result.prob_tp < 0.5
    assert result.decision in {"hold", "reject"}