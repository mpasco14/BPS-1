import json

from testnet_campaign.multi_session_review import build_multi_session_review


def test_multi_session_review_passes_clean_sessions(tmp_path):
    report_30 = tmp_path / "30min.json"
    report_2h = tmp_path / "2h.json"

    base = {
        "campaign_name": "campaign",
        "passed": True,
        "status": "PASS",
        "decision": "PROMOTE",
        "iterations_count": 2,
        "rejection_count": 0,
        "fill_count": 0,
        "final_flat_count": 2,
        "blockers": [],
        "warnings": [],
    }

    report_30.write_text(json.dumps({**base, "campaign_name": "30min"}), encoding="utf-8")
    report_2h.write_text(json.dumps({**base, "campaign_name": "2h"}), encoding="utf-8")

    review = build_multi_session_review(report_paths=[report_30, report_2h])

    assert review.passed is True
    assert review.decision == "READY_FOR_NEXT_GATE"
    assert review.sessions_count == 2


def test_multi_session_review_blocks_missing_report(tmp_path):
    review = build_multi_session_review(report_paths=[tmp_path / "missing.json"])

    assert review.passed is False
    assert any("session_report_missing" in item for item in review.blockers)