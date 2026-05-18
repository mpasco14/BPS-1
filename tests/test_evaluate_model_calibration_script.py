import json
from pathlib import Path

from scripts.evaluate_model_calibration import (
    build_demo_predictions,
    extract_calibration_arrays,
    load_prediction_rows,
    parse_probability,
    parse_target,
    run_calibration_evaluation_from_rows,
)


def test_build_demo_predictions():
    rows = build_demo_predictions()

    assert len(rows) >= 2
    assert "target" in rows[0]
    assert "prob_tp" in rows[0]


def test_parse_target_numeric():
    assert parse_target({"target": 1}) == 1
    assert parse_target({"y_true": 0}) == 0


def test_parse_target_outcome():
    assert parse_target({"outcome": "take_profit"}) == 1
    assert parse_target({"outcome": "stop_loss"}) == 0


def test_parse_probability_direct():
    assert parse_probability({"prob_tp": 0.7}) == 0.7
    assert parse_probability({"y_prob": 1.5}) == 1.0
    assert parse_probability({"probability": -0.5}) == 0.0


def test_parse_probability_nested():
    assert parse_probability({"prediction": {"calibrated_prob_tp": 0.8}}) == 0.8


def test_extract_calibration_arrays():
    rows = [
        {"target": 1, "prob_tp": 0.8},
        {"target": 0, "prob_tp": 0.2},
    ]

    y_true, y_prob = extract_calibration_arrays(rows)

    assert y_true == [1, 0]
    assert y_prob == [0.8, 0.2]


def test_load_prediction_rows_json(tmp_path: Path):
    path = tmp_path / "predictions.json"
    path.write_text(
        json.dumps(
            {
                "predictions": [
                    {"target": 1, "prob_tp": 0.8},
                    {"target": 0, "prob_tp": 0.2},
                ]
            }
        ),
        encoding="utf-8",
    )

    rows = load_prediction_rows(path)

    assert len(rows) == 2


def test_load_prediction_rows_jsonl(tmp_path: Path):
    path = tmp_path / "predictions.jsonl"
    path.write_text(
        '{"target":1,"prob_tp":0.8}\n{"target":0,"prob_tp":0.2}\n',
        encoding="utf-8",
    )

    rows = load_prediction_rows(path)

    assert len(rows) == 2


def test_run_calibration_evaluation_from_rows():
    rows = [
        {"target": 1, "prob_tp": 0.8},
        {"target": 0, "prob_tp": 0.2},
        {"target": 1, "prob_tp": 0.7},
        {"target": 0, "prob_tp": 0.3},
    ]

    report = run_calibration_evaluation_from_rows(
        rows,
        bins=2,
    )

    assert report.samples == 4
    assert report.brier_score >= 0
    assert report.expected_calibration_error >= 0