from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from scenario_testing.historical_market_replay import run_historical_market_replay
from scenario_testing.scenario_models import ScenarioTestReport, env_bool, generate_demo_candles


class NewsSentimentShockConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/scenario_testing")
    block_extreme: bool = True


def load_news_sentiment_shock_config() -> NewsSentimentShockConfig:
    return NewsSentimentShockConfig(
        output_dir=Path(os.getenv("NEWS_SENTIMENT_SHOCK_OUTPUT_DIR", "artifacts/scenario_testing")),
        block_extreme=env_bool("NEWS_SENTIMENT_BLOCK_EXTREME", True),
    )


def run_news_sentiment_shock_scenario(
    *,
    metadata: dict[str, Any] | None = None,
    config: NewsSentimentShockConfig | None = None,
) -> ScenarioTestReport:
    resolved_config = config or load_news_sentiment_shock_config()
    candles = generate_demo_candles(pattern="news_shock", count=12)

    replay = run_historical_market_replay(
        candles=candles,
        scenario_name="news_sentiment_shock_scenario",
        metadata={
            "scenario": "news_sentiment_shock",
            "block_extreme": resolved_config.block_extreme,
            **(metadata or {}),
        },
    )

    news_events = sum(1 for candle in candles if candle.news_event)
    sentiment_blocks = [
        step
        for step in replay.steps
        if any("extreme_fear" in blocker or "panic_score" in blocker for blocker in step["blockers"])
    ]

    blockers = list(replay.blockers)
    warnings = list(replay.warnings)

    if news_events == 0:
        blockers.append("news_shock_not_detected")

    if resolved_config.block_extreme and not sentiment_blocks:
        blockers.append("extreme_sentiment_did_not_block_entries")

    if sentiment_blocks:
        warnings.append("extreme_sentiment_blocks_confirmed")

    passed = not blockers

    status = "PASS" if passed and not warnings else "WARN" if passed else "FAIL"

    return replay.model_copy(
        update={
            "scenario_name": "news_sentiment_shock_scenario",
            "scenario_kind": "news_sentiment_shock",
            "status": status,
            "passed": passed,
            "blockers": blockers,
            "warnings": sorted(set(warnings)),
            "recommendations": [
                "Em choque de notícia/sentimento, priorizar preservação de capital.",
                "Validar bloqueios de sentimento extremo antes de qualquer sessão testnet/live.",
            ],
            "metadata": {
                **replay.metadata,
                "news_events": news_events,
                "sentiment_blocks": len(sentiment_blocks),
                "block_extreme": resolved_config.block_extreme,
            },
        }
    )