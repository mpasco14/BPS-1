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

__test__ = False


ReleaseStatus = Literal["PASS", "WARN", "FAIL", "BLOCKED"]
ReleaseDecision = Literal["READY_FOR_TAG", "BLOCKED", "REVIEW_REQUIRED"]


class PrivateReleaseConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/private_release")
    release_name: str = "v1.0.0-private"
    release_version: str = "1.0.0-private"

    require_git_clean: bool = True
    require_tests_passed: bool = True
    require_docs: bool = True
    require_artifacts: bool = False

    required_docs: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)

    operator_name: str = ""
    daily_checklist_confirmed: bool = False
    weekly_audit_confirmed: bool = False


class ComponentReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ReleaseStatus
    passed: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_csv(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)

    if not value:
        return default

    return [item.strip() for item in value.split(",") if item.strip()]


def load_private_release_config() -> PrivateReleaseConfig:
    return PrivateReleaseConfig(
        output_dir=Path(os.getenv("PRIVATE_RELEASE_OUTPUT_DIR", "artifacts/private_release")),
        release_name=os.getenv("PRIVATE_RELEASE_NAME", "v1.0.0-private"),
        release_version=os.getenv("PRIVATE_RELEASE_VERSION", "1.0.0-private"),
        require_git_clean=env_bool("PRIVATE_RELEASE_REQUIRE_GIT_CLEAN", True),
        require_tests_passed=env_bool("PRIVATE_RELEASE_REQUIRE_TESTS_PASSED", True),
        require_docs=env_bool("PRIVATE_RELEASE_REQUIRE_DOCS", True),
        require_artifacts=env_bool("PRIVATE_RELEASE_REQUIRE_ARTIFACTS", False),
        required_docs=env_csv(
            "PRIVATE_RELEASE_REQUIRED_DOCS",
            [
                "docs/README.md",
                "docs/ARCHITECTURE.md",
                "docs/LOCAL_SETUP_RUNBOOK.md",
                "docs/PAPER_TESTNET_RUNBOOK.md",
                "docs/CONTROLLED_LIVE_ACTIVATION_RUNBOOK.md",
                "docs/EMERGENCY_SHUTDOWN_RUNBOOK.md",
                "docs/WEEKLY_AUDIT_RUNBOOK.md",
            ],
        ),
        required_artifacts=env_csv(
            "PRIVATE_RELEASE_REQUIRED_ARTIFACTS",
            [
                "artifacts/v1_validation/logs/pytest_full.log",
                "artifacts/micro_live/micro_live_prep_gate_demo_go_no_go.json",
                "artifacts/micro_live_session/first_micro_live_dry_run_demo_report.json",
            ],
        ),
        operator_name=os.getenv("PRIVATE_RELEASE_OPERATOR_NAME", "").strip(),
        daily_checklist_confirmed=env_bool("PRIVATE_RELEASE_DAILY_CHECKLIST_CONFIRMED", False),
        weekly_audit_confirmed=env_bool("PRIVATE_RELEASE_WEEKLY_AUDIT_CONFIRMED", False),
    )


def sha256_file(path: str | Path) -> str:
    target = Path(path)
    digest = hashlib.sha256()

    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def export_release_json(
    payload: BaseModel | dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    name: str,
) -> Path:
    config = load_private_release_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path