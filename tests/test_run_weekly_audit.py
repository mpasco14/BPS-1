import json

from ops.retraining_protocol import ModelValidationMetrics
from scripts.run_weekly_audit import build_weekly_payload, export_weekly_payload, load_metrics_json


def test_load_metrics_json(tmp_path):
    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps(
            {
                "model_version": "candidate_v1",
                "samples": 1000,
                "brier_score": 0.1,
                "expected_calibration_error": 0.05,
                "net_pnl_usd": 100,
                "profit_factor": 1.5,
                "sharpe": 1.0,
                "max_drawdown_pct": 0.1,
            }
        ),
        encoding="utf-8",
    )

    metrics = load_metrics_json(path)

    assert metrics is not None
    assert metrics.model_version == "candidate_v1"


def test_build_weekly_payload_with_candidate():
    candidate = ModelValidationMetrics(
        model_version="candidate_v1",
        samples=1000,
        brier_score=0.1,
        expected_calibration_error=0.05,
        net_pnl_usd=100,
        profit_factor=1.5,
        sharpe=1.0,
        max_drawdown_pct=0.1,
    )

    payload = build_weekly_payload(candidate=candidate)

    assert payload["source"] == "weekly_audit_runner"
    assert "audit" in payload
    assert "retraining" in payload


def test_export_weekly_payload(tmp_path):
    payload = {
        "source": "weekly_audit_runner",
        "passed": True,
        "status": "PASS",
    }

    path = export_weekly_payload(
        payload,
        output_dir=tmp_path,
        name="unit_weekly",
    )

    assert path.exists()