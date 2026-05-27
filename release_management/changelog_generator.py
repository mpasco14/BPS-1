from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ChangeType = Literal["feature", "fix", "security", "docs", "test", "infra", "refactor", "other"]


class CommitRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    sha: str
    message: str
    author: str | None = None
    committed_at: datetime | None = None


class ChangelogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    change_type: ChangeType
    message: str
    sha: str | None = None


class ChangelogReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "changelog_generator"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    version: str
    entries_count: int
    entries: list[dict[str, Any]] = Field(default_factory=list)

    markdown: str


def classify_commit_message(message: str) -> ChangeType:
    lowered = message.lower().strip()

    if lowered.startswith(("feat", "add")):
        return "feature"

    if lowered.startswith(("fix", "bug")):
        return "fix"

    if lowered.startswith(("security", "sec")):
        return "security"

    if lowered.startswith(("docs", "doc")):
        return "docs"

    if lowered.startswith(("test", "tests")):
        return "test"

    if lowered.startswith(("infra", "ci", "build")):
        return "infra"

    if lowered.startswith(("refactor", "cleanup")):
        return "refactor"

    return "other"


def load_git_commits(
    *,
    limit: int | None = None,
) -> list[CommitRecord]:
    max_commits = limit or int(os.getenv("CHANGELOG_MAX_COMMITS", "50"))

    try:
        completed = subprocess.run(
            ["git", "log", f"-{max_commits}", "--pretty=format:%H%x1f%an%x1f%ad%x1f%s", "--date=iso-strict"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:
        return []

    if completed.returncode != 0:
        return []

    commits: list[CommitRecord] = []

    for line in completed.stdout.splitlines():
        parts = line.split("\x1f")

        if len(parts) < 4:
            continue

        sha, author, date_text, message = parts[:4]

        committed_at = None

        try:
            committed_at = datetime.fromisoformat(date_text)
        except ValueError:
            committed_at = None

        commits.append(
            CommitRecord(
                sha=sha,
                author=author,
                committed_at=committed_at,
                message=message,
            )
        )

    return commits


def generate_changelog_markdown(
    *,
    version: str,
    entries: list[ChangelogEntry],
) -> str:
    groups: dict[str, list[ChangelogEntry]] = {
        "feature": [],
        "fix": [],
        "security": [],
        "infra": [],
        "docs": [],
        "test": [],
        "refactor": [],
        "other": [],
    }

    for entry in entries:
        groups.setdefault(entry.change_type, []).append(entry)

    title = f"# Changelog — {version}"
    date_line = f"Generated at: {datetime.now(timezone.utc).isoformat()}"

    sections = [title, "", date_line, ""]

    labels = {
        "feature": "Features",
        "fix": "Fixes",
        "security": "Security",
        "infra": "Infrastructure / CI",
        "docs": "Documentation",
        "test": "Tests",
        "refactor": "Refactors",
        "other": "Other",
    }

    for group_key, label in labels.items():
        items = groups.get(group_key, [])

        if not items:
            continue

        sections.append(f"## {label}")
        sections.append("")

        for item in items:
            suffix = f" ({item.sha[:8]})" if item.sha else ""
            sections.append(f"- {item.message}{suffix}")

        sections.append("")

    if all(not items for items in groups.values()):
        sections.append("No changes detected.")
        sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def build_changelog_report(
    *,
    version: str,
    commits: list[CommitRecord | dict[str, Any]] | None = None,
) -> ChangelogReport:
    parsed_commits = [
        item if isinstance(item, CommitRecord) else CommitRecord.model_validate(item)
        for item in (commits if commits is not None else load_git_commits())
    ]

    entries = [
        ChangelogEntry(
            change_type=classify_commit_message(commit.message),
            message=commit.message,
            sha=commit.sha,
        )
        for commit in parsed_commits
    ]

    markdown = generate_changelog_markdown(version=version, entries=entries)

    return ChangelogReport(
        version=version,
        entries_count=len(entries),
        entries=[entry.model_dump(mode="json") for entry in entries],
        markdown=markdown,
    )


def export_changelog_report(
    report: ChangelogReport,
    *,
    output_dir: str | Path | None = None,
    name: str | None = None,
) -> tuple[Path, Path]:
    path = Path(output_dir or os.getenv("CHANGELOG_OUTPUT_DIR", "artifacts/release"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = (name or f"changelog_{report.version}").replace("/", "_").replace("\\", "_")

    json_path = path / f"{safe_name}.json"
    markdown_path = path / f"{safe_name}.md"

    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown_path.write_text(report.markdown, encoding="utf-8")

    return json_path, markdown_path