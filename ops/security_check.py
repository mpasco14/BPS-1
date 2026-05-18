"""
Security checks for Binance Futures bot.

Responsabilidades:
- Verificar .env fora do Git.
- Verificar artifacts/ ignorado.
- Verificar .env.example sem chaves reais.
- Verificar live trading bloqueado por padrão.
- Gerar relatório auditável.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


SecurityStatus = Literal["PASS", "WARN", "FAIL"]


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/ops")

    require_env_gitignored: bool = True
    require_artifacts_gitignored: bool = True
    require_no_secrets_in_example: bool = True
    require_live_trading_disabled_by_default: bool = True


class SecurityCheckItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: SecurityStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class SecurityReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "security_check"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    checks_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    blocking_fail_count: int

    checks: list[dict[str, Any]] = Field(default_factory=list)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_security_config() -> SecurityConfig:
    return SecurityConfig(
        output_dir=Path(os.getenv("OPS_OUTPUT_DIR", "artifacts/ops")),
        require_env_gitignored=env_bool("OPS_REQUIRE_ENV_GITIGNORED", True),
        require_artifacts_gitignored=env_bool("OPS_REQUIRE_ARTIFACTS_GITIGNORED", True),
        require_no_secrets_in_example=env_bool("OPS_REQUIRE_NO_SECRETS_IN_EXAMPLE", True),
        require_live_trading_disabled_by_default=env_bool("OPS_REQUIRE_LIVE_TRADING_DISABLED_BY_DEFAULT", True),
    )


def make_check(
    *,
    code: str,
    status: SecurityStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> SecurityCheckItem:
    return SecurityCheckItem(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def read_gitignore(path: str | Path = ".gitignore") -> str:
    file_path = Path(path)

    if not file_path.exists():
        return ""

    return file_path.read_text(encoding="utf-8")


def gitignore_has_pattern(pattern: str, *, gitignore_text: str | None = None) -> bool:
    text = gitignore_text if gitignore_text is not None else read_gitignore()
    lines = [line.strip() for line in text.splitlines()]

    return pattern in lines


def check_env_gitignored(config: SecurityConfig) -> SecurityCheckItem:
    if not config.require_env_gitignored:
        return make_check(
            code="ENV_GITIGNORE_NOT_REQUIRED",
            status="WARN",
            title=".env gitignore não obrigatório",
            message="OPS_REQUIRE_ENV_GITIGNORED está falso.",
        )

    text = read_gitignore()

    has_env = gitignore_has_pattern(".env", gitignore_text=text) or gitignore_has_pattern("*.env", gitignore_text=text)

    if has_env:
        return make_check(
            code="ENV_GITIGNORED",
            status="PASS",
            title=".env ignorado",
            message=".env está listado no .gitignore.",
            value=True,
        )

    return make_check(
        code="ENV_NOT_GITIGNORED",
        status="FAIL",
        title=".env não está no .gitignore",
        message="Inclua .env no .gitignore para evitar vazamento de credenciais.",
        value=False,
        expected=True,
        blocking=True,
    )


def check_artifacts_gitignored(config: SecurityConfig) -> SecurityCheckItem:
    if not config.require_artifacts_gitignored:
        return make_check(
            code="ARTIFACTS_GITIGNORE_NOT_REQUIRED",
            status="WARN",
            title="artifacts/ gitignore não obrigatório",
            message="OPS_REQUIRE_ARTIFACTS_GITIGNORED está falso.",
        )

    text = read_gitignore()

    has_artifacts = gitignore_has_pattern("artifacts/", gitignore_text=text)

    if has_artifacts:
        return make_check(
            code="ARTIFACTS_GITIGNORED",
            status="PASS",
            title="artifacts/ ignorado",
            message="artifacts/ está listado no .gitignore.",
            value=True,
        )

    return make_check(
        code="ARTIFACTS_NOT_GITIGNORED",
        status="FAIL",
        title="artifacts/ não está no .gitignore",
        message="Relatórios, datasets e modelos locais não devem ser versionados.",
        value=False,
        expected=True,
        blocking=True,
    )


def parse_env_example(path: str | Path = ".env.example") -> dict[str, str]:
    file_path = Path(path)

    if not file_path.exists():
        return {}

    values: dict[str, str] = {}

    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def looks_like_secret(value: str) -> bool:
    if not value:
        return False

    if value.lower() in {"changeme", "change_me", "example", "test", "none", "null"}:
        return False

    if len(value) >= 20 and re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
        return True

    if value.startswith("sk_") or value.startswith("pk_"):
        return True

    return False


def check_no_secrets_in_env_example(config: SecurityConfig) -> SecurityCheckItem:
    if not config.require_no_secrets_in_example:
        return make_check(
            code="NO_SECRETS_IN_EXAMPLE_NOT_REQUIRED",
            status="WARN",
            title="Checagem de secrets não obrigatória",
            message="OPS_REQUIRE_NO_SECRETS_IN_EXAMPLE está falso.",
        )

    values = parse_env_example()
    risky_keys = [
        key
        for key in values
        if any(token in key.upper() for token in ["SECRET", "PRIVATE", "API_KEY", "TOKEN", "PASSWORD"])
    ]

    exposed = {
        key: "***"
        for key in risky_keys
        if looks_like_secret(values.get(key, ""))
    }

    if exposed:
        return make_check(
            code="SECRETS_FOUND_IN_ENV_EXAMPLE",
            status="FAIL",
            title="Possíveis secrets encontrados no .env.example",
            message=".env.example não deve conter credenciais reais.",
            value=exposed,
            expected="empty_or_placeholder",
            blocking=True,
        )

    return make_check(
        code="NO_SECRETS_IN_ENV_EXAMPLE",
        status="PASS",
        title=".env.example sem secrets aparentes",
        message="Nenhum valor suspeito foi detectado em chaves sensíveis.",
        value=True,
    )


def check_live_trading_disabled(config: SecurityConfig) -> SecurityCheckItem:
    if not config.require_live_trading_disabled_by_default:
        return make_check(
            code="LIVE_TRADING_SECURITY_NOT_REQUIRED",
            status="WARN",
            title="Checagem de live trading não obrigatória",
            message="OPS_REQUIRE_LIVE_TRADING_DISABLED_BY_DEFAULT está falso.",
        )

    binance_live = env_bool("BINANCE_ALLOW_LIVE_TRADING", False)
    risk_live = env_bool("RISK_ALLOW_LIVE_TRADING", False)
    execution_mode = os.getenv("BINANCE_EXECUTION_MODE", "paper").strip().lower()

    if binance_live or risk_live or execution_mode == "live":
        return make_check(
            code="LIVE_TRADING_SECURITY_FAIL",
            status="FAIL",
            title="Live trading habilitado",
            message="Live trading não deve estar habilitado sem processo formal de aprovação.",
            value={
                "BINANCE_ALLOW_LIVE_TRADING": binance_live,
                "RISK_ALLOW_LIVE_TRADING": risk_live,
                "BINANCE_EXECUTION_MODE": execution_mode,
            },
            expected={
                "BINANCE_ALLOW_LIVE_TRADING": False,
                "RISK_ALLOW_LIVE_TRADING": False,
                "BINANCE_EXECUTION_MODE": "paper/testnet",
            },
            blocking=True,
        )

    return make_check(
        code="LIVE_TRADING_SECURITY_PASS",
        status="PASS",
        title="Live trading bloqueado",
        message="Live trading permanece desabilitado.",
        value={
            "BINANCE_ALLOW_LIVE_TRADING": binance_live,
            "RISK_ALLOW_LIVE_TRADING": risk_live,
            "BINANCE_EXECUTION_MODE": execution_mode,
        },
    )


def run_security_checks(config: SecurityConfig | None = None) -> SecurityReport:
    resolved_config = config or load_security_config()

    checks = [
        check_env_gitignored(resolved_config),
        check_artifacts_gitignored(resolved_config),
        check_no_secrets_in_env_example(resolved_config),
        check_live_trading_disabled(resolved_config),
    ]

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0

    return SecurityReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_security_report(
    report: SecurityReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "security_latest",
) -> Path:
    config = load_security_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path