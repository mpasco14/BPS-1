from pathlib import Path

from release_private.config_freeze import build_final_config_freeze_report


def test_config_freeze_detects_exposed_secret(tmp_path):
    config = tmp_path / ".env.example"
    config.write_text("API_SECRET=abc123\n", encoding="utf-8")

    report = build_final_config_freeze_report(config_files=[str(config)])

    assert report.passed is False
    assert any("exposed_secret_detected" in item for item in report.blockers)


def test_config_freeze_passes_empty_secret_placeholder(tmp_path):
    config = tmp_path / ".env.example"
    config.write_text("API_SECRET=\nAPI_KEY=\n", encoding="utf-8")

    report = build_final_config_freeze_report(config_files=[str(config)])

    assert report.passed is True