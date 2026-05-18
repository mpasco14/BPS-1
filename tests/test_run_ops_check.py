from scripts.run_ops_check import build_ops_payload, export_ops_payload


def test_build_ops_payload():
    payload = build_ops_payload()

    assert payload["source"] == "ops_check"
    assert "compliance" in payload
    assert "security" in payload
    assert payload["status"] in {"PASS", "FAIL"}


def test_export_ops_payload(tmp_path):
    payload = {
        "source": "ops_check",
        "passed": True,
        "status": "PASS",
    }

    path = export_ops_payload(
        payload,
        output_dir=tmp_path,
        name="unit_test_ops",
    )

    assert path.exists()