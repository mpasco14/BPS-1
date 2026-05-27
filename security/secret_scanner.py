from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


SecretSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class SecretScannerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/security")
    root_path: Path = Path(".")
    fail_on_findings: bool = True
    max_file_size_bytes: int = 1_000_000

    excluded_dirs: list[str] = Field(
        default_factory=lambda: [
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            ".pytest_cache",
            "node_modules",
            "artifacts",
            "dist",
            "build",
        ]
    )

    included_extensions: list[str] = Field(
        default_factory=lambda: [
            ".py",
            ".env",
            ".txt",
            ".md",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".ps1",
            ".sh",
        ]
    )


class SecretPattern(BaseModel):
    model_config = ConfigDict(extra="allow")

    pattern_id: str
    regex: str
    severity: SecretSeverity
    description: str


class SecretFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    pattern_id: str
    severity: SecretSeverity
    file_path: str
    line_number: int
    redacted_match: str
    context_hash: str
    blocking: bool = True


class SecretScanReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "secret_scanner"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    scanned_files_count: int
    findings_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    findings: list[dict[str, Any]] = Field(default_factory=list)
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


def load_secret_scanner_config() -> SecretScannerConfig:
    return SecretScannerConfig(
        output_dir=Path(os.getenv("SECRET_SCANNER_OUTPUT_DIR", "artifacts/security")),
        root_path=Path(os.getenv("SECRET_SCANNER_ROOT", ".")),
        fail_on_findings=env_bool("SECRET_SCANNER_FAIL_ON_FINDINGS", True),
        max_file_size_bytes=env_int("SECRET_SCANNER_MAX_FILE_SIZE_BYTES", 1_000_000),
    )


def default_secret_patterns() -> list[SecretPattern]:
    return [
        SecretPattern(
            pattern_id="private_key_block",
            regex=r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            severity="CRITICAL",
            description="Bloco de private key detectado.",
        ),
        SecretPattern(
            pattern_id="generic_api_key_assignment",
            regex=r"(?i)\b(api[_-]?key|api[_-]?secret|secret[_-]?key|private[_-]?key|access[_-]?token)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-/.+=]{16,}",
            severity="HIGH",
            description="Possível segredo em atribuição.",
        ),
        SecretPattern(
            pattern_id="binance_key_assignment",
            regex=r"(?i)\b(BINANCE_API_KEY|BINANCE_API_SECRET)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-/.+=]{16,}",
            severity="CRITICAL",
            description="Possível chave Binance em arquivo.",
        ),
        SecretPattern(
            pattern_id="aws_access_key",
            regex=r"\bAKIA[0-9A-Z]{16}\b",
            severity="HIGH",
            description="Possível AWS access key.",
        ),
    ]


def is_placeholder_line(line: str) -> bool:
    lowered = line.lower()

    placeholders = [
        "example",
        "placeholder",
        "changeme",
        "replace_me",
        "your_",
        "<",
        ">",
        "xxx",
        "dummy",
    ]

    return any(marker in lowered for marker in placeholders)


def redact(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)

    return f"{value[:4]}...{value[-4:]}"


def context_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def line_entropy(value: str) -> float:
    if not value:
        return 0.0

    counts = {char: value.count(char) for char in set(value)}
    length = len(value)

    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def scan_text_for_secrets(
    *,
    text: str,
    file_path: str = "<memory>",
    patterns: list[SecretPattern] | None = None,
) -> list[SecretFinding]:
    resolved_patterns = patterns or default_secret_patterns()
    findings: list[SecretFinding] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        if is_placeholder_line(line):
            continue

        for pattern in resolved_patterns:
            for match in re.finditer(pattern.regex, line):
                matched = match.group(0)

                findings.append(
                    SecretFinding(
                        pattern_id=pattern.pattern_id,
                        severity=pattern.severity,
                        file_path=file_path,
                        line_number=line_number,
                        redacted_match=redact(matched),
                        context_hash=context_hash(matched),
                        blocking=pattern.severity in {"HIGH", "CRITICAL"},
                    )
                )

    return findings


def should_scan_file(path: Path, config: SecretScannerConfig) -> bool:
    parts = set(path.parts)

    if any(excluded in parts for excluded in config.excluded_dirs):
        return False

    if path.suffix not in config.included_extensions and path.name != ".env":
        return False

    try:
        if path.stat().st_size > config.max_file_size_bytes:
            return False
    except OSError:
        return False

    return path.is_file()


def scan_file_for_secrets(
    path: str | Path,
    *,
    config: SecretScannerConfig | None = None,
) -> list[SecretFinding]:
    resolved_config = config or load_secret_scanner_config()
    file_path = Path(path)

    if not should_scan_file(file_path, resolved_config):
        return []

    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    return scan_text_for_secrets(text=text, file_path=str(file_path))


def scan_paths_for_secrets(
    *,
    paths: list[str | Path],
    config: SecretScannerConfig | None = None,
) -> SecretScanReport:
    resolved_config = config or load_secret_scanner_config()

    files: list[Path] = []

    for path_item in paths:
        path = Path(path_item)

        if path.is_file():
            if should_scan_file(path, resolved_config):
                files.append(path)
        elif path.is_dir():
            files.extend(
                file_path
                for file_path in path.rglob("*")
                if should_scan_file(file_path, resolved_config)
            )

    findings: list[SecretFinding] = []

    for file_path in sorted(set(files)):
        findings.extend(scan_file_for_secrets(file_path, config=resolved_config))

    critical = sum(1 for item in findings if item.severity == "CRITICAL")
    high = sum(1 for item in findings if item.severity == "HIGH")
    medium = sum(1 for item in findings if item.severity == "MEDIUM")
    low = sum(1 for item in findings if item.severity == "LOW")

    blockers = [
        f"{item.file_path}:{item.line_number}:{item.pattern_id}"
        for item in findings
        if item.blocking and resolved_config.fail_on_findings
    ]

    warnings = [
        f"{item.file_path}:{item.line_number}:{item.pattern_id}"
        for item in findings
        if not item.blocking or not resolved_config.fail_on_findings
    ]

    passed = not blockers

    return SecretScanReport(
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        scanned_files_count=len(files),
        findings_count=len(findings),
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
        blockers=blockers,
        warnings=warnings,
        findings=[item.model_dump(mode="json") for item in findings],
        config=resolved_config.model_dump(mode="json"),
    )


def build_secret_scan_report(
    *,
    root_path: str | Path | None = None,
    config: SecretScannerConfig | None = None,
) -> SecretScanReport:
    resolved_config = config or load_secret_scanner_config()
    root = Path(root_path or resolved_config.root_path)

    return scan_paths_for_secrets(paths=[root], config=resolved_config)


def export_secret_scan_report(
    report: SecretScanReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "secret_scan_latest",
) -> Path:
    config = load_secret_scanner_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path