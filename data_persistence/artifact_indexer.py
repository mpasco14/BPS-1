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


ArtifactKind = Literal["json", "jsonl", "markdown", "prometheus", "sqlite", "text", "other"]


class ArtifactIndexerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/storage")
    artifact_root: Path = Path("artifacts")
    index_file: Path = Path("artifacts/storage/artifact_index.json")

    hash_files: bool = False
    max_file_size_bytes: int = 5_000_000


class ArtifactIndexEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str
    name: str
    suffix: str
    kind: ArtifactKind

    size_bytes: int
    modified_at: datetime
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    sha256: str | None = None

    parent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactIndexReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "artifact_indexer"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    root: str
    artifacts_count: int
    total_size_bytes: int

    by_kind: dict[str, int] = Field(default_factory=dict)
    entries: list[dict[str, Any]] = Field(default_factory=list)
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


def load_artifact_indexer_config() -> ArtifactIndexerConfig:
    return ArtifactIndexerConfig(
        output_dir=Path(os.getenv("ARTIFACT_INDEXER_OUTPUT_DIR", "artifacts/storage")),
        artifact_root=Path(os.getenv("ARTIFACT_INDEXER_ROOT", "artifacts")),
        index_file=Path(os.getenv("ARTIFACT_INDEXER_FILE", "artifacts/storage/artifact_index.json")),
        hash_files=env_bool("ARTIFACT_INDEXER_HASH_FILES", False),
        max_file_size_bytes=env_int("ARTIFACT_INDEXER_MAX_FILE_SIZE_BYTES", 5_000_000),
    )


def artifact_kind_for_path(path: Path) -> ArtifactKind:
    suffix = path.suffix.lower()

    if suffix == ".json":
        return "json"

    if suffix == ".jsonl":
        return "jsonl"

    if suffix in {".md", ".markdown"}:
        return "markdown"

    if suffix == ".prom":
        return "prometheus"

    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return "sqlite"

    if suffix in {".txt", ".log"}:
        return "text"

    return "other"


def file_sha256(path: Path, *, max_file_size_bytes: int) -> str | None:
    try:
        if path.stat().st_size > max_file_size_bytes:
            return None

        digest = hashlib.sha256()

        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)

        return digest.hexdigest()

    except OSError:
        return None


def build_artifact_index_entry(
    path: Path,
    *,
    root: Path,
    config: ArtifactIndexerConfig,
) -> ArtifactIndexEntry | None:
    try:
        stat = path.stat()
    except OSError:
        return None

    if not path.is_file():
        return None

    relative = path.relative_to(root) if path.is_relative_to(root) else path

    digest = None
    if config.hash_files:
        digest = file_sha256(path, max_file_size_bytes=config.max_file_size_bytes)

    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    return ArtifactIndexEntry(
        path=str(relative).replace("\\", "/"),
        name=path.name,
        suffix=path.suffix.lower(),
        kind=artifact_kind_for_path(path),
        size_bytes=stat.st_size,
        modified_at=modified_at,
        sha256=digest,
        parent=str(relative.parent).replace("\\", "/") if str(relative.parent) != "." else None,
    )


def build_artifact_index_report(
    *,
    root: str | Path | None = None,
    config: ArtifactIndexerConfig | None = None,
) -> ArtifactIndexReport:
    resolved_config = config or load_artifact_indexer_config()
    resolved_root = Path(root or resolved_config.artifact_root)

    if not resolved_root.exists():
        return ArtifactIndexReport(
            root=str(resolved_root),
            artifacts_count=0,
            total_size_bytes=0,
            config=resolved_config.model_dump(mode="json"),
        )

    entries: list[ArtifactIndexEntry] = []

    for path in sorted(resolved_root.rglob("*")):
        entry = build_artifact_index_entry(path, root=resolved_root, config=resolved_config)

        if entry is not None:
            entries.append(entry)

    by_kind: dict[str, int] = {}

    for entry in entries:
        by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1

    return ArtifactIndexReport(
        root=str(resolved_root),
        artifacts_count=len(entries),
        total_size_bytes=sum(entry.size_bytes for entry in entries),
        by_kind=by_kind,
        entries=[entry.model_dump(mode="json") for entry in entries],
        config=resolved_config.model_dump(mode="json"),
    )


def export_artifact_index_report(
    report: ArtifactIndexReport,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_artifact_indexer_config()
    output_path = Path(path or config.index_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path