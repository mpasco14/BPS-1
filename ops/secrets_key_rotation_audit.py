from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


SecretAuditStatus = Literal["PASS", "WARN", "FAIL"]


class SecretsAuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/production")

    max_key_age_days: int = 30
    require_no_withdrawal_permission: bool = True
    require_rotation_date: bool = True
    warn_on_env_storage: bool = True


class SecretKeyRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    present: bool
    storage_backend: str = "env"
    last_rotated_at: datetime | None = None

    permissions: list[str] = Field(default_factory=list)

    is_placeholder: bool = False
    exposed_in_git: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)


class SecretAuditFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: SecretAuditStatus
    message: str
    secret_name: str | None = None
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class SecretsKeyRotationAuditReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "secrets_key_rotation_audit"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: SecretAuditStatus

    secrets_count: int
    findings_count: int
    blocking_findings_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    findings: list[dict[str, Any]] = Field(default_factory=list)
    secrets: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_secrets_audit_config() -> SecretsAuditConfig:
    return SecretsAuditConfig(
        output_dir=Path(os.getenv("SECRETS_AUDIT_OUTPUT_DIR", "artifacts/production")),
        max_key_age_days=env_int("SECRETS_AUDIT_MAX_KEY_AGE_DAYS", 30),
        require_no_withdrawal_permission=env_bool("SECRETS_AUDIT_REQUIRE_NO_WITHDRAWAL_PERMISSION", True),
        require_rotation_date=env_bool("SECRETS_AUDIT_REQUIRE_ROTATION_DATE", True),
        warn_on_env_storage=env_bool("SECRETS_AUDIT_WARN_ON_ENV_STORAGE", True),
    )


def looks_like_placeholder(value: str | None) -> bool:
    if not value:
        return True

    lowered = value.strip().lower()

    markers = [
        "changeme",
        "your_",
        "example",
        "placeholder",
        "test_key",
        "dummy",
        "replace_me",
    ]

    return any(marker in lowered for marker in markers)


def secret_record_from_env(
    *,
    env_name: str,
    permissions: list[str] | None = None,
    storage_backend: str = "env",
) -> SecretKeyRecord:
    value = os.getenv(env_name)

    return SecretKeyRecord(
        name=env_name,
        present=bool(value),
        storage_backend=storage_backend,
        permissions=permissions or [],
        is_placeholder=looks_like_placeholder(value),
        exposed_in_git=False,
        metadata={
            "redacted": True,
            "length": len(value) if value else 0,
        },
    )


def finding(
    *,
    code: str,
    status: SecretAuditStatus,
    message: str,
    secret_name: str | None = None,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> SecretAuditFinding:
    return SecretAuditFinding(
        code=code,
        status=status,
        message=message,
        secret_name=secret_name,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def audit_secret_record(
    secret: SecretKeyRecord,
    *,
    config: SecretsAuditConfig,
) -> list[SecretAuditFinding]:
    findings: list[SecretAuditFinding] = []

    if not secret.present:
        findings.append(
            finding(
                code="secret_missing",
                status="FAIL",
                message="Secret ausente.",
                secret_name=secret.name,
                value=False,
                expected=True,
                blocking=True,
            )
        )

    if secret.is_placeholder:
        findings.append(
            finding(
                code="secret_placeholder",
                status="FAIL",
                message="Secret parece placeholder/dummy.",
                secret_name=secret.name,
                value=True,
                expected=False,
                blocking=True,
            )
        )

    if secret.exposed_in_git:
        findings.append(
            finding(
                code="secret_exposed_in_git",
                status="FAIL",
                message="Secret marcado como exposto no Git.",
                secret_name=secret.name,
                value=True,
                expected=False,
                blocking=True,
            )
        )

    if config.warn_on_env_storage and secret.storage_backend == "env":
        findings.append(
            finding(
                code="secret_in_env_storage",
                status="WARN",
                message="Secret em variável de ambiente. Para produção madura, preferir vault/secrets manager.",
                secret_name=secret.name,
                value=secret.storage_backend,
                expected="vault",
                blocking=False,
            )
        )

    if config.require_rotation_date and secret.last_rotated_at is None:
        findings.append(
            finding(
                code="rotation_date_missing",
                status="WARN",
                message="Data de rotação ausente.",
                secret_name=secret.name,
                expected="last_rotated_at",
                blocking=False,
            )
        )

    if secret.last_rotated_at is not None:
        rotated = secret.last_rotated_at
        if rotated.tzinfo is None:
            rotated = rotated.replace(tzinfo=timezone.utc)

        age_days = (datetime.now(timezone.utc) - rotated).total_seconds() / 86400

        if age_days > config.max_key_age_days:
            findings.append(
                finding(
                    code="secret_rotation_overdue",
                    status="FAIL",
                    message="Secret acima da idade máxima permitida.",
                    secret_name=secret.name,
                    value=round(age_days, 2),
                    expected=f"<={config.max_key_age_days}",
                    blocking=True,
                )
            )

    if config.require_no_withdrawal_permission:
        forbidden = {"withdraw", "withdrawal", "transfer"}
        matched = sorted(set(item.lower() for item in secret.permissions) & forbidden)

        if matched:
            findings.append(
                finding(
                    code="secret_has_forbidden_permission",
                    status="FAIL",
                    message="Chave com permissão proibida para trading bot.",
                    secret_name=secret.name,
                    value=matched,
                    expected="no_withdrawal_or_transfer_permissions",
                    blocking=True,
                )
            )

    return findings


def build_secrets_key_rotation_audit_report(
    *,
    secrets: list[SecretKeyRecord | dict[str, Any]] | None = None,
    config: SecretsAuditConfig | None = None,
) -> SecretsKeyRotationAuditReport:
    resolved_config = config or load_secrets_audit_config()

    if secrets is None:
        api_key_name = os.getenv("BINANCE_API_KEY_NAME", "BINANCE_API_KEY")
        api_secret_name = os.getenv("BINANCE_API_SECRET_NAME", "BINANCE_API_SECRET")

        parsed = [
            secret_record_from_env(env_name=api_key_name, permissions=["trade", "read"]),
            secret_record_from_env(env_name=api_secret_name, permissions=["trade", "read"]),
        ]
    else:
        parsed = [
            item if isinstance(item, SecretKeyRecord) else SecretKeyRecord.model_validate(item)
            for item in secrets
        ]

    findings: list[SecretAuditFinding] = []

    for secret in parsed:
        findings.extend(audit_secret_record(secret, config=resolved_config))

    blockers = [item.code for item in findings if item.blocking]
    warnings = [item.code for item in findings if item.status == "WARN"]

    passed = not blockers

    if blockers:
        status: SecretAuditStatus = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    return SecretsKeyRotationAuditReport(
        passed=passed,
        status=status,
        secrets_count=len(parsed),
        findings_count=len(findings),
        blocking_findings_count=len(blockers),
        blockers=blockers,
        warnings=warnings,
        findings=[item.model_dump(mode="json") for item in findings],
        secrets=[item.model_dump(mode="json") for item in parsed],
        config=resolved_config.model_dump(mode="json"),
    )


def export_secrets_key_rotation_audit_report(
    report: SecretsKeyRotationAuditReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "secrets_key_rotation_audit_latest",
) -> Path:
    config = load_secrets_audit_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path