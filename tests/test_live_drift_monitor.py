from data.learning_feedback_dataset import LearningFeedbackRow
from models.live_drift_monitor import LiveDriftConfig, build_live_drift_report, export_live_drift_report


def stable_rows():
    rows = []

    for index in range(30):
        target = 1 if index % 3 != 0 else 0
        prob = 0.75 if target == 1 else 0.25

        rows.append(
            LearningFeedbackRow(
                decision_id=f"stable_{index}",
                final_decision="ENTER",
                model_probability=prob,
                model_confidence=prob,
                target=target,
                is_win=bool(target),
                ood_detected=False,
            )
        )

    return rows


def test_live_drift_monitor_stable():
    report = build_live_drift_report(
        rows=stable_rows(),
        config=LiveDriftConfig(min_samples=20),
    )

    assert report.passed is True
    assert report.status in {"STABLE", "WATCH"}


def test_live_drift_monitor_blocks_ood_rate():
    rows = stable_rows()

    for row in rows:
        row.ood_detected = True

    report = build_live_drift_report(
        rows=rows,
        config=LiveDriftConfig(max_ood_rate=0.20),
    )

    assert report.passed is False
    assert "ood_rate_above_limit" in report.blockers


def test_export_live_drift_report(tmp_path):
    report = build_live_drift_report(rows=stable_rows())

    path = export_live_drift_report(
        report,
        output_dir=tmp_path,
        name="unit_drift",
    )

    assert path.exists()