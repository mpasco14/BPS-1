from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


RetentionAction = Literal["KEEP", "DELETE"]
RetentionStatus = Literal["PASS", "WARN", "FAIL"]


class RetentionPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/storage")

    dry_run: bool = True
    max_age_days: int = 30
    protected_dirs: list[str] = Field(default_factory=lambda: ["artifacts/security", "artifacts/production", "artifacts/release"])


class RetentionCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str
    size_bytes: int
    age_days: float

    action: RetentionAction
    reason: str

    protected: bool = False
    deleted: bool = False
    error: str | None = None


class RetentionPolicyReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "data_retention_policy"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: RetentionStatus
    passed: bool
    dry_run: bool

    scanned_files_count: int
    delete_candidates_count: int
    deleted_count: int
    protected_count: int
    errors_count: int

    reclaimed_bytes: int = 0
    candidates: list[dict[str, Any]] = Field(default_factory=list)
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


def load_retention_policy_config() -> RetentionPolicyConfig:
    protected_raw = os.getenv("RETENTION_POLICY_PROTECTED_DIRS", "artifacts/security,artifacts/production,artifacts/release")

    protected_dirs = [
        item.strip()
        for item in protected_raw.split(",")
        if item.strip()
    ]

    return RetentionPolicyConfig(
        output_dir=Path(os.getenv("RETENTION_POLICY_OUTPUT_DIR", "artifacts/storage")),
        dry_run=env_bool("RETENTION_POLICY_DRY_RUN", True),
        max_age_days=env_int("RETENTION_POLICY_MAX_AGE_DAYS", 30),
        protected_dirs=protected_dirs,
    )


def file_age_days(path: Path, *, now: datetime | None = None) -> float:
    resolved_now = now or datetime.now(timezone.utc)
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    return max(0.0, (resolved_now - modified_at).total_seconds() / 86400)


def is_protected_path(path: Path, protected_dirs: list[str]) -> bool:
    resolved = path.resolve()

    for protected in protected_dirs:
        protected_path = Path(protected).resolve()

        try:
            resolved.relative_to(protected_path)
            return True
        except ValueError:
            continue

    return False


def evaluate_retention_candidate(
    *,
    path: Path,
    root: Path,
    config: RetentionPolicyConfig,
    now: datetime | None = None,
) -> RetentionCandidate | None:
    if not path.is_file():
        return None

    try:
        stat = path.stat()
        age = file_age_days(path, now=now)
    except OSError:
        return None

    relative = path.relative_to(root) if path.is_relative_to(root) else path
    protected = is_protected_path(path, config.protected_dirs)

    if protected:
        return RetentionCandidate(
            path=str(relative).replace("\\", "/"),
            size_bytes=stat.st_size,
            age_days=round(age, 4),
            action="KEEP",
            reason="protected_path",
            protected=True,
        )

    if age > config.max_age_days:
        return RetentionCandidate(
            path=str(relative).replace("\\", "/"),
            size_bytes=stat.st_size,
            age_days=round(age, 4),
            action="DELETE",
            reason="older_than_max_age",
            protected=False,
        )

    return RetentionCandidate(
        path=str(relative).replace("\\", "/"),
        size_bytes=stat.st_size,
        age_days=round(age, 4),
        action="KEEP",
        reason="within_retention_window",
        protected=False,
    )


def evaluate_retention_policy(
    *,
    root: str | Path = "artifacts",
    config: RetentionPolicyConfig | None = None,
    now: datetime | None = None,
) -> RetentionPolicyReport:
    resolved_config = config or load_retention_policy_config()
    root_path = Path(root)

    if not root_path.exists():
        return RetentionPolicyReport(
            status="PASS",
            passed=True,
            dry_run=resolved_config.dry_run,
            scanned_files_count=0,
            delete_candidates_count=0,
            deleted_count=0,
            protected_count=0,
            errors_count=0,
            config=resolved_config.model_dump(mode="json"),
        )

    candidates: list[RetentionCandidate] = []

    for path in sorted(root_path.rglob("*")):
        candidate = evaluate_retention_candidate(
            path=path,
            root=root_path,
            config=resolved_config,
            now=now,
        )

        if candidate is not None:
            candidates.append(candidate)

    deleted_count = 0
    errors_count = 0
    reclaimed_bytes = 0

    for candidate in candidates:
        if candidate.action != "DELETE":
            continue

        target = root_path / candidate.path

        if resolved_config.dry_run:
            continue

        try:
            target.unlink()
            candidate.deleted = True
            deleted_count += 1
            reclaimed_bytes += candidate.size_bytes
        except OSError as exc:
            candidate.error = str(exc)
            errors_count += 1

    delete_candidates = [item for item in candidates if item.action == "DELETE"]
    protected_count = sum(1 for item in candidates if item.protected)

    passed = errors_count == 0

    return RetentionPolicyReport(
        status="PASS" if passed else "FAIL",
        passed=passed,
        dry_run=resolved_config.dry_run,
        scanned_files_count=len(candidates),
        delete_candidates_count=len(delete_candidates),
        deleted_count=deleted_count,
        protected_count=protected_count,
        errors_count=errors_count,
        reclaimed_bytes=reclaimed_bytes,
        candidates=[item.model_dump(mode="json") for item in candidates],
        config=resolved_config.model_dump(mode="json"),
    )


def export_retention_policy_report(
    report: RetentionPolicyReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "retention_policy_latest",
) -> Path:
    config = load_retention_policy_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path