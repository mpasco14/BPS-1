from ops.retraining_protocol import (
    ModelValidationMetrics,
    RetrainingProtocolConfig,
    evaluate_retraining_candidate,
    export_retraining_report,
)


def good_candidate():
    return ModelValidationMetrics(
        model_version="candidate_v1",
        samples=1000,
        brier_score=0.10,
        expected_calibration_error=0.05,
        net_pnl_usd=100,
        roi_pct=0.05,
        profit_factor=1.5,
        sharpe=1.0,
        max_drawdown_pct=0.10,
    )


def weaker_current():
    return ModelValidationMetrics(
        model_version="current_v1",
        samples=1000,
        brier_score=0.12,
        expected_calibration_error=0.08,
        net_pnl_usd=50,
        roi_pct=0.02,
        profit_factor=1.2,
        sharpe=0.8,
        max_drawdown_pct=0.12,
    )


def test_good_candidate_is_approved():
    report = evaluate_retraining_candidate(
        candidate=good_candidate(),
        current=weaker_current(),
        config=RetrainingProtocolConfig(),
    )

    assert report.passed is True
    assert report.decision == "APPROVED"
    assert report.promotion_recommended is True
    assert report.auto_promote_allowed is False


def test_candidate_with_bad_calibration_is_rejected():
    candidate = good_candidate()
    candidate.expected_calibration_error = 0.30

    report = evaluate_retraining_candidate(
        candidate=candidate,
        current=weaker_current(),
        config=RetrainingProtocolConfig(),
    )

    assert report.passed is False
    assert report.decision == "REJECTED"


def test_candidate_worse_than_current_is_rejected():
    candidate = good_candidate()
    candidate.net_pnl_usd = 10

    current = weaker_current()
    current.net_pnl_usd = 100

    report = evaluate_retraining_candidate(
        candidate=candidate,
        current=current,
        config=RetrainingProtocolConfig(),
    )

    assert report.passed is False
    assert any(check["code"] == "CANDIDATE_PNL_WORSE" for check in report.checks)


def test_export_retraining_report(tmp_path):
    report = evaluate_retraining_candidate(
        candidate=good_candidate(),
        current=weaker_current(),
        config=RetrainingProtocolConfig(),
    )

    path = export_retraining_report(
        report,
        output_dir=tmp_path,
        name="unit_retraining",
    )

    assert path.exists()