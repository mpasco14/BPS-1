from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


NoTradeAction = Literal["ALLOW_TRADE", "NO_TRADE"]


class NoTradeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/governance")

    min_confidence: float = 0.65
    min_expected_value_usd: float = 0.0
    max_spread_pct: float = 0.002
    min_liquidity_usd: float = 50_000
    max_consecutive_losses: int = 3

    blocked_regimes: list[str] = Field(
        default_factory=lambda: ["UNTRADEABLE", "HIGH_VOLATILITY", "LOW_LIQUIDITY", "NEWS_SHOCK"]
    )

    require_data_quality_pass: bool = True
    block_on_ood: bool = True
    block_on_kill_switch: bool = True
    require_risk_state_ok: bool = True


class NoTradeInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    timeframe: str | None = None
    side: str | None = None

    data_quality_passed: bool = True
    data_quality_blockers: list[str] = Field(default_factory=list)

    model_confidence: float | None = None
    expected_value_usd: float | None = None
    model_ood: bool = False

    spread_pct: float | None = None
    liquidity_usd: float | None = None
    regime: str | None = None

    risk_state_status: str | None = "OK"
    consecutive_losses: int = 0
    kill_switch_active: bool = False

    extra_context: dict[str, Any] = Field(default_factory=dict)


class NoTradeDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "no_trade_engine"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    action: NoTradeAction
    should_trade: bool

    symbol: str
    timeframe: str | None = None
    side: str | None = None

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    input: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


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


def load_no_trade_config() -> NoTradeConfig:
    regimes = [
        item.strip().upper()
        for item in os.getenv(
            "NO_TRADE_BLOCKED_REGIMES",
            "UNTRADEABLE,HIGH_VOLATILITY,LOW_LIQUIDITY,NEWS_SHOCK",
        ).split(",")
        if item.strip()
    ]

    return NoTradeConfig(
        output_dir=Path(os.getenv("NO_TRADE_OUTPUT_DIR", "artifacts/governance")),
        min_confidence=env_float("NO_TRADE_MIN_CONFIDENCE", 0.65),
        min_expected_value_usd=env_float("NO_TRADE_MIN_EXPECTED_VALUE_USD", 0.0),
        max_spread_pct=env_float("NO_TRADE_MAX_SPREAD_PCT", 0.002),
        min_liquidity_usd=env_float("NO_TRADE_MIN_LIQUIDITY_USD", 50_000),
        max_consecutive_losses=env_int("NO_TRADE_MAX_CONSECUTIVE_LOSSES", 3),
        blocked_regimes=regimes,
        require_data_quality_pass=env_bool("NO_TRADE_REQUIRE_DATA_QUALITY_PASS", True),
        block_on_ood=env_bool("NO_TRADE_BLOCK_ON_OOD", True),
        block_on_kill_switch=env_bool("NO_TRADE_BLOCK_ON_KILL_SWITCH", True),
        require_risk_state_ok=env_bool("NO_TRADE_REQUIRE_RISK_STATE_OK", True),
    )


def evaluate_no_trade(
    *,
    input_data: NoTradeInput | dict[str, Any],
    config: NoTradeConfig | None = None,
) -> NoTradeDecision:
    data = input_data if isinstance(input_data, NoTradeInput) else NoTradeInput.model_validate(input_data)
    resolved_config = config or load_no_trade_config()

    blockers: list[str] = []
    warnings: list[str] = []

    if resolved_config.block_on_kill_switch and data.kill_switch_active:
        blockers.append("kill_switch_active")

    if resolved_config.require_data_quality_pass and not data.data_quality_passed:
        blockers.append("data_quality_failed")
        blockers.extend(data.data_quality_blockers)

    if resolved_config.block_on_ood and data.model_ood:
        blockers.append("model_ood_detected")

    if data.model_confidence is None:
        blockers.append("model_confidence_missing")
    elif data.model_confidence < resolved_config.min_confidence:
        blockers.append("model_confidence_below_minimum")

    if data.expected_value_usd is None:
        blockers.append("expected_value_missing")
    elif data.expected_value_usd <= resolved_config.min_expected_value_usd:
        blockers.append("expected_value_not_positive_enough")

    if data.spread_pct is None:
        blockers.append("spread_missing")
    elif data.spread_pct > resolved_config.max_spread_pct:
        blockers.append("spread_above_limit")

    if data.liquidity_usd is None:
        blockers.append("liquidity_missing")
    elif data.liquidity_usd < resolved_config.min_liquidity_usd:
        blockers.append("liquidity_below_minimum")

    if data.regime and data.regime.upper() in resolved_config.blocked_regimes:
        blockers.append(f"blocked_regime:{data.regime.upper()}")

    if resolved_config.require_risk_state_ok and data.risk_state_status != "OK":
        blockers.append("risk_state_not_ok")

    if data.consecutive_losses >= resolved_config.max_consecutive_losses:
        blockers.append("max_consecutive_losses_reached")

    if data.regime is None:
        warnings.append("regime_missing")

    should_trade = len(blockers) == 0

    return NoTradeDecision(
        action="ALLOW_TRADE" if should_trade else "NO_TRADE",
        should_trade=should_trade,
        symbol=data.symbol,
        timeframe=data.timeframe,
        side=data.side,
        blockers=blockers,
        warnings=warnings,
        input=data.model_dump(mode="json"),
    )


def export_no_trade_decision(
    decision: NoTradeDecision,
    *,
    output_dir: str | Path | None = None,
    name: str = "no_trade_decision_latest",
) -> Path:
    config = load_no_trade_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path