from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


VersionBump = Literal["major", "minor", "patch", "prerelease"]


SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


class SemanticVersion(BaseModel):
    model_config = ConfigDict(extra="allow")

    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"

        if self.prerelease:
            base = f"{base}-{self.prerelease}"

        if self.build:
            base = f"{base}+{self.build}"

        return base


class VersionPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/release")
    current_version: str = "0.17.0"
    allow_prerelease: bool = True


class VersionPolicyReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "semantic_versioning_policy"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    valid: bool
    current_version: str
    suggested_next_version: str | None = None
    bump: VersionBump | None = None

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_version_policy_config() -> VersionPolicyConfig:
    return VersionPolicyConfig(
        output_dir=Path(os.getenv("RELEASE_OUTPUT_DIR", "artifacts/release")),
        current_version=os.getenv("RELEASE_CURRENT_VERSION", "0.17.0"),
        allow_prerelease=env_bool("RELEASE_ALLOW_PRERELEASE", True),
    )


def parse_semantic_version(version: str) -> SemanticVersion:
    match = SEMVER_RE.match(version.strip())

    if not match:
        raise ValueError(f"Invalid semantic version: {version}")

    return SemanticVersion(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        prerelease=match.group("prerelease"),
        build=match.group("build"),
    )


def is_valid_semantic_version(version: str) -> bool:
    try:
        parse_semantic_version(version)
        return True
    except ValueError:
        return False


def bump_semantic_version(version: str, bump: VersionBump) -> str:
    parsed = parse_semantic_version(version)

    if bump == "major":
        return str(SemanticVersion(major=parsed.major + 1, minor=0, patch=0))

    if bump == "minor":
        return str(SemanticVersion(major=parsed.major, minor=parsed.minor + 1, patch=0))

    if bump == "patch":
        return str(SemanticVersion(major=parsed.major, minor=parsed.minor, patch=parsed.patch + 1))

    if bump == "prerelease":
        base = SemanticVersion(major=parsed.major, minor=parsed.minor, patch=parsed.patch)

        if not parsed.prerelease:
            base.prerelease = "rc.1"
            return str(base)

        parts = parsed.prerelease.split(".")

        if parts and parts[-1].isdigit():
            parts[-1] = str(int(parts[-1]) + 1)
            base.prerelease = ".".join(parts)
        else:
            base.prerelease = f"{parsed.prerelease}.1"

        return str(base)

    raise ValueError(f"Unsupported bump: {bump}")


def evaluate_version_policy(
    *,
    current_version: str | None = None,
    bump: VersionBump = "patch",
    config: VersionPolicyConfig | None = None,
) -> VersionPolicyReport:
    resolved_config = config or load_version_policy_config()
    version = current_version or resolved_config.current_version

    blockers: list[str] = []
    warnings: list[str] = []

    try:
        parsed = parse_semantic_version(version)
    except ValueError:
        return VersionPolicyReport(
            valid=False,
            current_version=version,
            bump=bump,
            blockers=["invalid_semantic_version"],
        )

    if parsed.prerelease and not resolved_config.allow_prerelease:
        blockers.append("prerelease_not_allowed")

    suggested = None

    if not blockers:
        suggested = bump_semantic_version(version, bump)

    return VersionPolicyReport(
        valid=not blockers,
        current_version=version,
        suggested_next_version=suggested,
        bump=bump,
        blockers=blockers,
        warnings=warnings,
    )