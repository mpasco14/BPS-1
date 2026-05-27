from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


class FeatureFlagConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/config")
    flags_file: Path = Path("artifacts/config/feature_flags.json")
    environment: str = "development"


class FeatureFlag(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    enabled: bool = False

    environments: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)

    rollout_percentage: float = 100.0

    description: str | None = None
    owner: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureFlagContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    environment: str = "development"
    symbol: str | None = None
    session_id: str = "default"
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureFlagDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "feature_flag_engine"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    flag_name: str
    enabled: bool

    reason: str
    rollout_bucket: float | None = None

    context: dict[str, Any]
    flag: dict[str, Any]


class FeatureFlagEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "feature_flag_evaluation"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    flags_count: int
    enabled_count: int
    disabled_count: int

    decisions: list[dict[str, Any]] = Field(default_factory=list)


def load_feature_flag_config() -> FeatureFlagConfig:
    return FeatureFlagConfig(
        output_dir=Path(os.getenv("FEATURE_FLAGS_OUTPUT_DIR", "artifacts/config")),
        flags_file=Path(os.getenv("FEATURE_FLAGS_FILE", "artifacts/config/feature_flags.json")),
        environment=os.getenv("FEATURE_FLAGS_ENVIRONMENT", "development"),
    )


def normalize_flag_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def stable_rollout_bucket(*, flag_name: str, context: FeatureFlagContext) -> float:
    identity = context.user_id or context.session_id or "default"
    raw = f"{normalize_flag_name(flag_name)}:{identity}:{context.symbol or ''}:{context.environment}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) % 10_000

    return value / 100.0


def evaluate_feature_flag(
    *,
    flag: FeatureFlag | dict[str, Any],
    context: FeatureFlagContext | dict[str, Any],
) -> FeatureFlagDecision:
    parsed_flag = flag if isinstance(flag, FeatureFlag) else FeatureFlag.model_validate(flag)
    parsed_context = context if isinstance(context, FeatureFlagContext) else FeatureFlagContext.model_validate(context)

    normalized_name = normalize_flag_name(parsed_flag.name)

    if not parsed_flag.enabled:
        return FeatureFlagDecision(
            flag_name=normalized_name,
            enabled=False,
            reason="flag_disabled",
            context=parsed_context.model_dump(mode="json"),
            flag=parsed_flag.model_dump(mode="json"),
        )

    if parsed_flag.environments and parsed_context.environment not in parsed_flag.environments:
        return FeatureFlagDecision(
            flag_name=normalized_name,
            enabled=False,
            reason="environment_not_allowed",
            context=parsed_context.model_dump(mode="json"),
            flag=parsed_flag.model_dump(mode="json"),
        )

    if parsed_flag.symbols and parsed_context.symbol and parsed_context.symbol not in parsed_flag.symbols:
        return FeatureFlagDecision(
            flag_name=normalized_name,
            enabled=False,
            reason="symbol_not_allowed",
            context=parsed_context.model_dump(mode="json"),
            flag=parsed_flag.model_dump(mode="json"),
        )

    bucket = stable_rollout_bucket(flag_name=normalized_name, context=parsed_context)
    rollout = max(0.0, min(100.0, parsed_flag.rollout_percentage))

    if bucket >= rollout:
        return FeatureFlagDecision(
            flag_name=normalized_name,
            enabled=False,
            reason="outside_rollout_percentage",
            rollout_bucket=bucket,
            context=parsed_context.model_dump(mode="json"),
            flag=parsed_flag.model_dump(mode="json"),
        )

    return FeatureFlagDecision(
        flag_name=normalized_name,
        enabled=True,
        reason="enabled",
        rollout_bucket=bucket,
        context=parsed_context.model_dump(mode="json"),
        flag=parsed_flag.model_dump(mode="json"),
    )


def evaluate_feature_flags(
    *,
    flags: list[FeatureFlag | dict[str, Any]],
    context: FeatureFlagContext | dict[str, Any],
) -> FeatureFlagEvaluationReport:
    decisions = [
        evaluate_feature_flag(flag=flag, context=context)
        for flag in flags
    ]

    enabled_count = sum(1 for item in decisions if item.enabled)

    return FeatureFlagEvaluationReport(
        flags_count=len(decisions),
        enabled_count=enabled_count,
        disabled_count=len(decisions) - enabled_count,
        decisions=[item.model_dump(mode="json") for item in decisions],
    )


def build_default_feature_flags() -> list[FeatureFlag]:
    config = load_feature_flag_config()

    return [
        FeatureFlag(
            name="sentiment_intelligence",
            enabled=True,
            environments=[config.environment, "paper", "testnet", "development"],
            symbols=["BTCUSDT"],
            rollout_percentage=100,
            description="Enable sentiment features.",
        ),
        FeatureFlag(
            name="live_order_submission",
            enabled=False,
            environments=["production"],
            symbols=["BTCUSDT"],
            rollout_percentage=0,
            description="Final live order submission flag. Must stay disabled by default.",
        ),
        FeatureFlag(
            name="adaptive_threshold_review",
            enabled=True,
            environments=[config.environment, "paper", "testnet", "development"],
            rollout_percentage=100,
            description="Enable adaptive threshold review.",
        ),
    ]


def export_feature_flags(
    flags: list[FeatureFlag],
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_feature_flag_config()
    output_path = Path(path or config.flags_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = [item.model_dump(mode="json") for item in flags]

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def load_feature_flags(path: str | Path | None = None) -> list[FeatureFlag]:
    config = load_feature_flag_config()
    input_path = Path(path or config.flags_file)

    if not input_path.exists():
        return build_default_feature_flags()

    payload = json.loads(input_path.read_text(encoding="utf-8"))

    return [FeatureFlag.model_validate(item) for item in payload]