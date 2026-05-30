from __future__ import annotations

from pathlib import Path
from typing import Any

from release_private.release_models import ComponentReport, export_release_json, sha256_file


DEFAULT_CONFIG_FILES = [
    ".env.example",
    "requirements.txt",
    "requirements.lock.txt",
    "README.md",
]


SENSITIVE_KEYS = [
    "API_SECRET",
    "SECRET_KEY",
    "PRIVATE_KEY",
    "PASSWORD",
    "TOKEN",
]


def line_has_exposed_secret(line: str) -> bool:
    stripped = line.strip()

    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return False

    key, value = stripped.split("=", 1)
    normalized_key = key.upper().strip()
    value = value.strip()

    if not value:
        return False

    if value in {"CHANGE_ME", "changeme", "...", "***", "your_key_here", "your_secret_here"}:
        return False

    return any(sensitive in normalized_key for sensitive in SENSITIVE_KEYS)


def scan_config_file_for_exposed_secrets(path: Path) -> list[str]:
    findings: list[str] = []

    if not path.exists():
        return findings

    for index, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        if line_has_exposed_secret(line):
            key = line.split("=", 1)[0].strip()
            findings.append(f"{path}:{index}:{key}")

    return findings


def build_final_config_freeze_report(
    *,
    config_files: list[str] | None = None,
) -> ComponentReport:
    files = config_files or DEFAULT_CONFIG_FILES

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    frozen_files: list[dict[str, Any]] = []

    for item in files:
        path = Path(item)

        if not path.exists():
            warnings.append(f"config_file_missing:{item}")
            continue

        exposed = scan_config_file_for_exposed_secrets(path)

        if exposed:
            blockers.append(f"exposed_secret_detected:{item}")

        frozen_files.append(
            {
                "path": item,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "secret_findings": exposed,
            }
        )

    recommendations.append("Manter .env fora do Git.")
    recommendations.append("Registrar hash dos arquivos de configuração usados na V1 privada.")
    recommendations.append("Qualquer alteração em config após freeze exige nova validação.")

    passed = not blockers

    return ComponentReport(
        source="private_release_final_config_freeze",
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        metadata={"frozen_files": frozen_files},
    )


def export_final_config_freeze_report(
    report: ComponentReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "private_release_config_freeze",
) -> Path:
    return export_release_json(report, output_dir=output_dir, name=name)