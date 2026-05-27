from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


StrategyProfileMode = Literal["conservative", "balanced", "aggressive", "custom"]
ProfileValidationStatus = Literal["PASS", "WARN", "FAIL"]


class StrategyProfilesConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/config")
    profiles_file: Path = Path("artifacts/config/strategy_profiles.json")

    default_profile: str = "conservative"
    max_leverage: int = 30
    max_margin_usd: float = 20.0
    max_risk_multiplier: float = 1.0


class StrategyParameterProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    mode: StrategyProfileMode = "conservative"

    max_leverage: int = 10
    max_margin_usd: float = 5.0
    max_notional_usd: float = 150.0

    risk_multiplier: float = 0.25

    min_confidence: float = 0.60
    min_edge: float = 0.01
    max_slippage_pct: float = 0.002

    allowed_timeframes: list[str] = Field(default_factory=lambda: ["5m", "15m"])
    timeframe_weights: dict[str, float] = Field(default_factory=lambda: {"5m": 0.5, "15m": 0.5})

    sentiment_enabled: bool = True
    no_trade_strictness: float = 1.0

    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyProfileValidationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "strategy_profile_validation"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    profile_name: str
    status: ProfileValidationStatus
    passed: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    profile: dict[str, Any]
    config: dict[str, Any]


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_strategy_profiles_config() -> StrategyProfilesConfig:
    return StrategyProfilesConfig(
        output_dir=Path(os.getenv("STRATEGY_PROFILES_OUTPUT_DIR", "artifacts/config")),
        profiles_file=Path(os.getenv("STRATEGY_PROFILES_FILE", "artifacts/config/strategy_profiles.json")),
        default_profile=os.getenv("STRATEGY_PROFILE_DEFAULT", "conservative"),
        max_leverage=env_int("STRATEGY_PROFILE_MAX_LEVERAGE", 30),
        max_margin_usd=env_float("STRATEGY_PROFILE_MAX_MARGIN_USD", 20),
        max_risk_multiplier=env_float("STRATEGY_PROFILE_MAX_RISK_MULTIPLIER", 1.0),
    )


def build_default_strategy_profiles() -> list[StrategyParameterProfile]:
    return [
        StrategyParameterProfile(
            name="conservative",
            mode="conservative",
            max_leverage=5,
            max_margin_usd=5,
            max_notional_usd=100,
            risk_multiplier=0.20,
            min_confidence=0.65,
            min_edge=0.015,
            allowed_timeframes=["5m", "15m"],
            timeframe_weights={"5m": 0.4, "15m": 0.6},
            no_trade_strictness=1.2,
        ),
        StrategyParameterProfile(
            name="balanced",
            mode="balanced",
            max_leverage=10,
            max_margin_usd=10,
            max_notional_usd=250,
            risk_multiplier=0.50,
            min_confidence=0.60,
            min_edge=0.01,
            allowed_timeframes=["5m", "15m", "1h"],
            timeframe_weights={"5m": 0.3, "15m": 0.4, "1h": 0.3},
            no_trade_strictness=1.0,
        ),
        StrategyParameterProfile(
            name="aggressive",
            mode="aggressive",
            max_leverage=20,
            max_margin_usd=20,
            max_notional_usd=600,
            risk_multiplier=1.0,
            min_confidence=0.57,
            min_edge=0.008,
            allowed_timeframes=["5m", "15m", "1h"],
            timeframe_weights={"5m": 0.4, "15m": 0.35, "1h": 0.25},
            no_trade_strictness=0.8,
        ),
    ]


def validate_strategy_profile(
    *,
    profile: StrategyParameterProfile | dict[str, Any],
    config: StrategyProfilesConfig | None = None,
) -> StrategyProfileValidationReport:
    resolved_config = config or load_strategy_profiles_config()
    parsed = profile if isinstance(profile, StrategyParameterProfile) else StrategyParameterProfile.model_validate(profile)

    blockers: list[str] = []
    warnings: list[str] = []

    if parsed.max_leverage > resolved_config.max_leverage:
        blockers.append("max_leverage_above_global_limit")

    if parsed.max_margin_usd > resolved_config.max_margin_usd:
        blockers.append("max_margin_above_global_limit")

    if parsed.risk_multiplier > resolved_config.max_risk_multiplier:
        blockers.append("risk_multiplier_above_global_limit")

    if parsed.min_confidence < 0.50:
        blockers.append("min_confidence_too_low")

    if parsed.min_edge < 0:
        blockers.append("min_edge_negative")

    if not parsed.allowed_timeframes:
        blockers.append("allowed_timeframes_empty")

    weight_sum = sum(parsed.timeframe_weights.values())

    if parsed.timeframe_weights and abs(weight_sum - 1.0) > 0.001:
        warnings.append("timeframe_weights_do_not_sum_to_one")

    missing_weights = [
        timeframe
        for timeframe in parsed.allowed_timeframes
        if timeframe not in parsed.timeframe_weights
    ]

    if missing_weights:
        warnings.append("timeframe_weights_missing_allowed_timeframes")

    passed = not blockers

    return StrategyProfileValidationReport(
        profile_name=parsed.name,
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        blockers=blockers,
        warnings=warnings,
        profile=parsed.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def select_strategy_profile(
    *,
    profiles: list[StrategyParameterProfile | dict[str, Any]],
    name: str | None = None,
) -> StrategyParameterProfile:
    config = load_strategy_profiles_config()
    target = name or config.default_profile

    parsed = [
        item if isinstance(item, StrategyParameterProfile) else StrategyParameterProfile.model_validate(item)
        for item in profiles
    ]

    for profile in parsed:
        if profile.name == target:
            return profile

    raise ValueError(f"Strategy profile not found: {target}")


def export_strategy_profiles(
    profiles: list[StrategyParameterProfile],
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_strategy_profiles_config()
    output_path = Path(path or config.profiles_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in profiles], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def load_strategy_profiles(path: str | Path | None = None) -> list[StrategyParameterProfile]:
    config = load_strategy_profiles_config()
    input_path = Path(path or config.profiles_file)

    if not input_path.exists():
        return build_default_strategy_profiles()

    payload = json.loads(input_path.read_text(encoding="utf-8"))

    return [StrategyParameterProfile.model_validate(item) for item in payload]