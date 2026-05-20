from data.learning_feedback_dataset import LearningFeedbackRow
from ops.threshold_review import (
    ThresholdReviewConfig,
    build_threshold_review_report,
    export_threshold_review_report,
)


def rows(win_rate_good: bool = True):
    output = []

    for index in range(25):
        is_win = True if win_rate_good else index < 5

        output.append(
            LearningFeedbackRow(
                decision_id=f"decision_{index}",
                trade_id=f"trade_{index}",
                symbol="BTCUSDT",
                timeframe="5m",
                side="BUY",
                final_decision="ENTER",
                model_confidence=0.70,
                expected_value_usd=0.20,
                realized_net_pnl_usd=1.0 if is_win else -1.0,
                is_win=is_win,
                target=1 if is_win else 0,
            )
        )

    return output


def test_threshold_review_keep_thresholds():
    report = build_threshold_review_report(
        rows=rows(win_rate_good=True),
        config=ThresholdReviewConfig(min_samples=20, min_win_rate=0.52),
    )

    assert report.recommendations[0]["action"] == "KEEP_THRESHOLDS"


def test_threshold_review_increase_confidence():
    report = build_threshold_review_report(
        rows=rows(win_rate_good=False),
        config=ThresholdReviewConfig(min_samples=20, min_win_rate=0.52),
    )

    assert report.recommendations[0]["action"] == "INCREASE_MIN_CONFIDENCE"


def test_export_threshold_review_report(tmp_path):
    report = build_threshold_review_report(
        rows=rows(),
        config=ThresholdReviewConfig(min_samples=20),
    )

    path = export_threshold_review_report(
        report,
        output_dir=tmp_path,
        name="unit_threshold_review",
    )

    assert path.exists()