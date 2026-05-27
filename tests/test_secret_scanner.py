from security.secret_scanner import scan_text_for_secrets, scan_paths_for_secrets, SecretScannerConfig


def test_secret_scanner_detects_api_key_assignment():
    findings = scan_text_for_secrets(
        text="BINANCE_API_KEY=abc12345678901234567890",
        file_path="unit.env",
    )

    assert findings
    assert findings[0].severity in {"HIGH", "CRITICAL"}


def test_secret_scanner_ignores_placeholder():
    findings = scan_text_for_secrets(
        text="BINANCE_API_KEY=your_api_key_here",
        file_path=".env.example",
    )

    assert findings == []


def test_secret_scanner_report_blocks_finding(tmp_path):
    file_path = tmp_path / "leak.env"
    file_path.write_text("API_SECRET=abc12345678901234567890", encoding="utf-8")

    report = scan_paths_for_secrets(
        paths=[tmp_path],
        config=SecretScannerConfig(root_path=tmp_path, fail_on_findings=True),
    )

    assert report.passed is False
    assert report.findings_count == 1