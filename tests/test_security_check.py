from ops.security_check import (
    SecurityConfig,
    check_no_secrets_in_env_example,
    gitignore_has_pattern,
    looks_like_secret,
    parse_env_example,
    run_security_checks,
    export_security_report,
)


def test_gitignore_has_pattern():
    assert gitignore_has_pattern(".env", gitignore_text=".env\nartifacts/\n") is True
    assert gitignore_has_pattern("missing", gitignore_text=".env\n") is False


def test_looks_like_secret():
    assert looks_like_secret("") is False
    assert looks_like_secret("changeme") is False
    assert looks_like_secret("abc12345678901234567890") is True


def test_parse_env_example(tmp_path):
    path = tmp_path / ".env.example"
    path.write_text("A=1\n# comment\nB=2\n", encoding="utf-8")

    values = parse_env_example(path)

    assert values["A"] == "1"
    assert values["B"] == "2"


def test_no_secrets_in_env_example_pass(tmp_path, monkeypatch):
    path = tmp_path / ".env.example"
    path.write_text("BINANCE_FUTURES_API_SECRET=\nTOKEN=changeme\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    result = check_no_secrets_in_env_example(SecurityConfig())

    assert result.status == "PASS"


def test_run_security_checks():
    report = run_security_checks(
        SecurityConfig(
            require_env_gitignored=False,
            require_artifacts_gitignored=False,
            require_no_secrets_in_example=False,
        )
    )

    assert report.checks_count >= 1
    assert report.status in {"PASS", "FAIL"}


def test_export_security_report(tmp_path):
    report = run_security_checks(
        SecurityConfig(
            require_env_gitignored=False,
            require_artifacts_gitignored=False,
            require_no_secrets_in_example=False,
        )
    )

    path = export_security_report(
        report,
        output_dir=tmp_path,
    )

    assert path.exists()