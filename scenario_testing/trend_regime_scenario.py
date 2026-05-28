from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from scenario_testing.historical_market_replay import run_historical_market_replay
from scenario_testing.scenario_models import ScenarioTestReport, env_float, generate_demo_candles


TrendDirection = Literal["uptrend", "downtrend"]


class TrendRegimeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/scenario_testing")
    min_directional_signal_ratio: float = 0.60


def load_trend_regime_config() -> TrendRegimeConfig:
    return TrendRegimeConfig(
        output_dir=Path(os.getenv("TREND_REGIME_OUTPUT_DIR", "artifacts/scenario_testing")),
        min_directional_signal_ratio=env_float("TREND_REGIME_MIN_DIRECTIONAL_SIGNAL_RATIO", 0.60),
    )


def run_trend_regime_scenario(
    *,
    trend_direction: TrendDirection = "uptrend",
    metadata: dict[str, Any] | None = None,
    config: TrendRegimeConfig | None = None,
) -> ScenarioTestReport:
    resolved_config = config or load_trend_regime_config()
    candles = generate_demo_candles(pattern=trend_direction, count=12)

    replay = run_historical_market_replay(
        candles=candles,
        scenario_name=f"trend_regime_scenario_{trend_direction}",
        metadata={
            "scenario": "trend_regime",
            "trend_direction": trend_direction,
            **(metadata or {}),
        },
    )

    directional_steps = [
        step
        for step in replay.steps
        if step["direction"] != "HOLD"
    ]

    ratio = 0.0
    if replay.steps_count > 0:
        ratio = len(directional_steps) / replay.steps_count

    blockers = list(replay.blockers)
    warnings = list(replay.warnings)

    if ratio < resolved_config.min_directional_signal_ratio:
        blockers.append("directional_signal_ratio_below_minimum")

    passed = not blockers

    status = "PASS" if passed and not warnings else "WARN" if passed else "FAIL"

    return replay.model_copy(
        update={
            "scenario_name": f"trend_regime_scenario_{trend_direction}",
            "scenario_kind": "trend_regime",
            "status": status,
            "passed": passed,
            "blockers": blockers,
            "warnings": warnings,
            "recommendations": [
                "Validar se o sistema acompanha tendência sem elevar risco automaticamente.",
                "Comparar performance de trend_up e trend_down antes de testnet.",
            ],
            "metadata": {
                **replay.metadata,
                "trend_direction": trend_direction,
                "directional_signal_ratio": round(ratio, 8),
                "min_directional_signal_ratio": resolved_config.min_directional_signal_ratio,
            },
        }
    )