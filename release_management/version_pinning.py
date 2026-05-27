from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


PinKind = Literal["model", "config", "dataset", "code", "artifact"]


class VersionPin(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    kind: PinKind
    version: str
    path: str | None = None
    sha256: str | None = None

    required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReleaseVersionManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "release_version_manifest"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    release_version: str
    git_commit: str | None = None

    pins: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VersionManifestValidationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "version_manifest_validation"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    release_version: str
    passed: bool
    status: str

    pins_count: int
    missing_required_pins: list[str] = Field(default_factory=list)
    missing_hash_pins: list[str] = Field(default_factory=list)

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    manifest: dict[str, Any]


def file_sha256(path: str | Path) -> str | None:
    file_path = Path(path)

    if not file_path.exists() or not file_path.is_file():
        return None

    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def build_version_pin(
    *,
    name: str,
    kind: PinKind,
    version: str,
    path: str | None = None,
    required: bool = True,
    metadata: dict[str, Any] | None = None,
) -> VersionPin:
    digest = file_sha256(path) if path else None

    return VersionPin(
        name=name,
        kind=kind,
        version=version,
        path=path,
        sha256=digest,
        required=required,
        metadata=metadata or {},
    )


def build_release_version_manifest(
    *,
    release_version: str,
    pins: list[VersionPin | dict[str, Any]],
    git_commit: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ReleaseVersionManifest:
    parsed = [
        pin if isinstance(pin, VersionPin) else VersionPin.model_validate(pin)
        for pin in pins
    ]

    return ReleaseVersionManifest(
        release_version=release_version,
        git_commit=git_commit,
        pins=[pin.model_dump(mode="json") for pin in parsed],
        metadata=metadata or {},
    )


def validate_version_manifest(
    manifest: ReleaseVersionManifest | dict[str, Any],
    *,
    required_kinds: list[PinKind] | None = None,
    require_hash_for_required: bool = False,
) -> VersionManifestValidationReport:
    parsed = manifest if isinstance(manifest, ReleaseVersionManifest) else ReleaseVersionManifest.model_validate(manifest)
    required = required_kinds or ["model", "config", "code"]

    pins = [VersionPin.model_validate(item) for item in parsed.pins]

    kinds_present = {pin.kind for pin in pins if pin.required}
    missing_required = [kind for kind in required if kind not in kinds_present]

    missing_hash = [
        pin.name
        for pin in pins
        if pin.required and require_hash_for_required and not pin.sha256
    ]

    blockers: list[str] = []
    warnings: list[str] = []

    if missing_required:
        blockers.append("required_pin_kind_missing")

    if missing_hash:
        warnings.append("required_pin_hash_missing")

    passed = not blockers

    return VersionManifestValidationReport(
        release_version=parsed.release_version,
        passed=passed,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        pins_count=len(pins),
        missing_required_pins=missing_required,
        missing_hash_pins=missing_hash,
        blockers=blockers,
        warnings=warnings,
        manifest=parsed.model_dump(mode="json"),
    )


def export_version_manifest(
    manifest: ReleaseVersionManifest,
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or os.getenv("VERSION_MANIFEST_FILE", "artifacts/release/version_manifest.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def export_version_manifest_validation_report(
    report: VersionManifestValidationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "version_manifest_validation_latest",
) -> Path:
    path = Path(output_dir or os.getenv("VERSION_MANIFEST_OUTPUT_DIR", "artifacts/release"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path