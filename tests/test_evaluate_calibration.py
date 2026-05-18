import numpy as np

from models.evaluate_calibration import (
    brier_score_metric,
    build_calibration_buckets,
    evaluate_probability_calibration,
    expected_calibration_error,
    export_calibration_report,
)


def test_brier_score_metric():
    y = [0, 1]
    p = [0.1, 0.9]

    assert brier_score_metric(y, p) < 0.02


def test_build_calibration_buckets():
    y = [0, 0, 1, 1]
    p = [0.1, 0.2, 0.8, 0.9]

    buckets = build_calibration_buckets(y, p, n_bins=2)

    assert len(buckets) == 2
    assert buckets[0].count == 2
    assert buckets[1].count == 2


def test_expected_calibration_error():
    y = [0, 0, 1, 1]
    p = [0.1, 0.2, 0.8, 0.9]

    ece = expected_calibration_error(y, p, n_bins=2)

    assert 0 <= ece <= 1


def test_evaluate_probability_calibration():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.3, 0.7, 0.9])

    report = evaluate_probability_calibration(
        y_true=y,
        y_prob=p,
        n_bins=4,
    )

    assert report.samples == 4
    assert report.buckets_count == 4
    assert report.brier_score >= 0
    assert report.expected_calibration_error >= 0


def test_export_calibration_report(tmp_path):
    report = evaluate_probability_calibration(
        y_true=[0, 1],
        y_prob=[0.2, 0.8],
        n_bins=2,
    )

    path = export_calibration_report(
        report,
        output_dir=tmp_path,
    )

    assert path.exists()