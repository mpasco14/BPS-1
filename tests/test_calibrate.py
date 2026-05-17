import numpy as np

from models.calibrate import (
    apply_calibration,
    brier_score,
    fit_calibrator,
    fit_isotonic_calibrator,
    fit_platt_calibrator,
    load_calibrator,
    save_calibrator,
)


def test_fit_platt_calibrator():
    y = np.array([0, 0, 1, 1], dtype=float)
    p = np.array([0.1, 0.3, 0.7, 0.9], dtype=float)

    artifact = fit_platt_calibrator(y_true=y, y_prob=p, epochs=100)
    calibrated = apply_calibration(artifact, p)

    assert artifact.method == "platt"
    assert len(calibrated) == 4
    assert all(0 <= value <= 1 for value in calibrated)


def test_fit_isotonic_calibrator():
    y = np.array([0, 0, 1, 1], dtype=float)
    p = np.array([0.1, 0.3, 0.7, 0.9], dtype=float)

    artifact = fit_isotonic_calibrator(y_true=y, y_prob=p)
    calibrated = apply_calibration(artifact, p)

    assert artifact.method == "isotonic"
    assert len(calibrated) == 4
    assert all(0 <= value <= 1 for value in calibrated)


def test_fit_calibrator_dispatch():
    y = np.array([0, 1], dtype=float)
    p = np.array([0.2, 0.8], dtype=float)

    artifact = fit_calibrator(
        y_true=y,
        y_prob=p,
        method="platt",
    )

    assert artifact.method == "platt"


def test_brier_score():
    y = np.array([0, 1], dtype=float)
    p = np.array([0.1, 0.9], dtype=float)

    assert brier_score(y, p) < 0.02


def test_save_and_load_calibrator(tmp_path):
    y = np.array([0, 1], dtype=float)
    p = np.array([0.2, 0.8], dtype=float)

    artifact = fit_platt_calibrator(
        y_true=y,
        y_prob=p,
        epochs=50,
    )

    path = save_calibrator(artifact, tmp_path / "calibrator.json")
    loaded = load_calibrator(path)

    assert loaded.method == artifact.method