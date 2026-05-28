from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from scenario_testing.historical_market_replay import HistoricalReplayConfig, run_historical_market_replay
from scenario_testing.scenario_models import ScenarioTestReport, env_float, generate_demo_candles


class ChopSidewaysConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/scenario_testing")
    max_signal_ratio: float = 0.50
    max_abs_pnl_usd: float = 5.0


def load_chop_sideways_config() -> ChopSidewaysConfig:
    return ChopSidewaysConfig(
        output_dir=Path(os.getenv("CHOP_SIDEWAYS_OUTPUT_DIR", "artifacts/scenario_testing")),
        max_signal_ratio=env_float("CHOP_MAX_SIGNAL_RATIO", 0.50),
        max_abs_pnl_usd=env_float("CHOP_MAX_ABS_PNL_USD", 5),
    )


def run_chop_sideways_scenario(
    *,
    metadata: dict[str, Any] | None = None,
    config: ChopSidewaysConfig | None = None,
) -> ScenarioTestReport:
    resolved_config = config or load_chop_sideways_config()
    candles = generate_demo_candles(pattern="sideways", count=12)

    replay = run_historical_market_replay(
        candles=candles,
        scenario_name="chop_sideways_scenario",
        config=HistoricalReplayConfig(min_abs_move_for_signal_pct=0.002),
        metadata={
            "scenario": "chop_sideways",
            **(metadata or {}),
        },
    )

    signal_ratio = 0.0
    if replay.steps_count > 0:
        signal_ratio = replay.approved_signals_count / replay.steps_count

    blockers = list(replay.blockers)
    warnings = list(replay.warnings)

    if signal_ratio > resolved_config.max_signal_ratio:
        blockers.append("sideways_signal_ratio_above_limit")

    if abs(replay.total_pnl_usd) > resolved_config.max_abs_pnl_usd:
        warnings.append("sideways_abs_pnl_above_expected_range")

    passed = not blockers

    status = "PASS" if passed and not warnings else "WARN" if passed else "FAIL"

    return replay.model_copy(
        update={
            "scenario_name": "chop_sideways_scenario",
            "scenario_kind": "chop_sideways",
            "status": status,
            "passed": passed,
            "blockers": blockers,
            "warnings": warnings,
            "recommendations": [
                "Em mercado lateral, o sistema deve evitar overtrading.",
                "Se gerar sinais demais em chop, aumentar thresholds ou usar no-trade engine mais restritivo.",
            ],
            "metadata": {
                **replay.metadata,
                "signal_ratio": round(signal_ratio, 8),
                "max_signal_ratio": resolved_config.max_signal_ratio,
                "max_abs_pnl_usd": resolved_config.max_abs_pnl_usd,
            },
        }
    )