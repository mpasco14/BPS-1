from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from release_private.release_models import ComponentReport, PrivateReleaseConfig, export_release_json, load_private_release_config


class ReleaseLockInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    branch: str = "main"
    git_clean: bool = True
    upstream_synced: bool = True
    tests_passed: bool = False
    tag_exists: bool = False
    release_version: str = "1.0.0-private"


def run_git_command(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except OSError:
        return ""


def inspect_release_lock_inputs(
    *,
    release_version: str = "1.0.0-private",
    tests_passed: bool = False,
) -> ReleaseLockInputs:
    branch = run_git_command(["branch", "--show-current"]) or "unknown"
    status = run_git_command(["status", "--porcelain"])
    tags = run_git_command(["tag", "--list", release_version])

    behind_ahead = run_git_command(["rev-list", "--left-right", "--count", "HEAD...@{upstream}"])
    upstream_synced = True

    if behind_ahead:
        parts = behind_ahead.split()
        if len(parts) == 2:
            ahead, behind = parts
            upstream_synced = ahead == "0" and behind == "0"

    return ReleaseLockInputs(
        branch=branch,
        git_clean=status == "",
        upstream_synced=upstream_synced,
        tests_passed=tests_passed,
        tag_exists=tags.strip() == release_version,
        release_version=release_version,
    )


def evaluate_release_lock(
    *,
    inputs: ReleaseLockInputs | dict[str, Any] | None = None,
    config: PrivateReleaseConfig | None = None,
) -> ComponentReport:
    resolved = config or load_private_release_config()
    parsed = (
        inputs
        if isinstance(inputs, ReleaseLockInputs)
        else ReleaseLockInputs.model_validate(inputs)
        if inputs is not None
        else inspect_release_lock_inputs(
            release_version=resolved.release_version,
            tests_passed=False,
        )
    )

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if parsed.branch != "main":
        warnings.append("release_not_on_main_branch")

    if resolved.require_git_clean and not parsed.git_clean:
        blockers.append("git_working_tree_not_clean")

    if not parsed.upstream_synced:
        blockers.append("branch_not_synced_with_upstream")

    if resolved.require_tests_passed and not parsed.tests_passed:
        blockers.append("full_test_suite_not_confirmed")

    if parsed.tag_exists:
        blockers.append("release_tag_already_exists")

    recommendations.append("Criar tag somente após pytest completo, artifacts e runbooks revisados.")
    recommendations.append("Não commitar arquivos .env nem artifacts sensíveis.")

    passed = not blockers

    return ComponentReport(
        source="private_release_lock",
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        metadata=parsed.model_dump(mode="json"),
    )


def export_release_lock_report(
    report: ComponentReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "private_release_lock",
) -> Path:
    return export_release_json(report, output_dir=output_dir, name=name)