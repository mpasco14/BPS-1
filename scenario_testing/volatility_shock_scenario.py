from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from scenario_testing.historical_market_replay import HistoricalReplayConfig, run_historical_market_replay
from scenario_testing.scenario_models import ScenarioTestReport, env_float, generate_demo_candles, pct_change


class VolatilityShockConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/scenario_testing")
    shock_threshold_pct: float = 0.015
    max_allowed_drawdown_pct: float = 0.04


def load_volatility_shock_config() -> VolatilityShockConfig:
    return VolatilityShockConfig(
        output_dir=Path(os.getenv("VOLATILITY_SHOCK_OUTPUT_DIR", "artifacts/scenario_testing")),
        shock_threshold_pct=env_float("VOLATILITY_SHOCK_THRESHOLD_PCT", 0.015),
        max_allowed_drawdown_pct=env_float("VOLATILITY_SHOCK_MAX_ALLOWED_DRAWDOWN_PCT", 0.04),
    )


def run_volatility_shock_scenario(
    *,
    metadata: dict[str, Any] | None = None,
    config: VolatilityShockConfig | None = None,
) -> ScenarioTestReport:
    resolved_config = config or load_volatility_shock_config()

    candles = generate_demo_candles(pattern="volatility", count=12)

    shock_events = 0
    for index in range(1, len(candles)):
        if abs(pct_change(candles[index - 1].close, candles[index].close)) >= resolved_config.shock_threshold_pct:
            shock_events += 1

    replay = run_historical_market_replay(
        candles=candles,
        scenario_name="volatility_shock_scenario",
        config=HistoricalReplayConfig(max_drawdown_pct=resolved_config.max_allowed_drawdown_pct),
        metadata={
            "scenario": "volatility_shock",
            "shock_threshold_pct": resolved_config.shock_threshold_pct,
            "shock_events": shock_events,
            **(metadata or {}),
        },
    )

    warnings = list(replay.warnings)

    if shock_events > 0:
        warnings.append("volatility_shock_detected")

    blockers = list(replay.blockers)

    if shock_events == 0:
        blockers.append("volatility_shock_not_detected")

    passed = not blockers

    status = "PASS" if passed and not warnings else "WARN" if passed else "FAIL"

    return replay.model_copy(
        update={
            "scenario_name": "volatility_shock_scenario",
            "scenario_kind": "volatility_shock",
            "status": status,
            "passed": passed,
            "blockers": blockers,
            "warnings": sorted(set(warnings)),
            "recommendations": [
                "Em choque de volatilidade, manter dry-run/testnet até validar slippage e fill rate.",
                "Se drawdown exceder limite, reduzir notional, leverage ou pausar entradas.",
            ],
            "metadata": {
                **replay.metadata,
                "shock_events": shock_events,
                "shock_threshold_pct": resolved_config.shock_threshold_pct,
            },
        }
    )