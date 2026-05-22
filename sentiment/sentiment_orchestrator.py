from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from sentiment.fear_greed import FearGreedReport, build_fear_greed_report
from sentiment.preprocessor import PreprocessConfig, preprocess_sentiment_items
from sentiment.sentiment_index import SentimentIndexReport, build_sentiment_index
from sentiment.sentiment_schema import CleanSentimentItem, RawSentimentItem, SentimentClassification
from sentiment.source_weighting import apply_source_weights


load_dotenv()


BULLISH_TERMS = {
    "bullish",
    "pump",
    "breakout",
    "moon",
    "accumulation",
    "support held",
    "etf inflow",
    "buy pressure",
    "short squeeze",
    "alta",
    "rompimento",
    "suporte segurou",
    "pressão compradora",
    "bullish_rocket",
    "bullish_moon",
    "bullish_chart_up",
}

BEARISH_TERMS = {
    "bearish",
    "dump",
    "breakdown",
    "selloff",
    "resistance rejected",
    "liquidation cascade",
    "panic",
    "fear",
    "queda",
    "rompimento para baixo",
    "resistência",
    "pânico",
    "liquidação",
    "bearish_chart_down",
    "bearish_blood",
    "bearish_fear",
}


class SentimentOrchestratorReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_orchestrator"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    asset: str = "BTCUSDT"
    timeframe: str = "5m"

    raw_items_count: int = 0
    clean_items_count: int = 0
    classified_items_count: int = 0

    sentiment_index: dict[str, Any]
    fear_greed: dict[str, Any]
    classifications: list[dict[str, Any]] = Field(default_factory=list)
    preprocess: dict[str, Any] = Field(default_factory=dict)


def classify_text(item: CleanSentimentItem) -> SentimentClassification:
    text = item.clean_text

    bullish_hits = sum(1 for term in BULLISH_TERMS if term in text)
    bearish_hits = sum(1 for term in BEARISH_TERMS if term in text)

    total_hits = bullish_hits + bearish_hits

    if total_hits == 0:
        sentiment = "neutral"
        score = 0.0
        confidence = 0.35
        reason = "no_directional_terms"
    elif bullish_hits > bearish_hits:
        sentiment = "bullish"
        score = min(1.0, (bullish_hits - bearish_hits) / max(1, total_hits))
        confidence = min(0.95, 0.50 + total_hits * 0.10)
        reason = "bullish_terms_dominant"
    elif bearish_hits > bullish_hits:
        sentiment = "bearish"
        score = -min(1.0, (bearish_hits - bullish_hits) / max(1, total_hits))
        confidence = min(0.95, 0.50 + total_hits * 0.10)
        reason = "bearish_terms_dominant"
    else:
        sentiment = "neutral"
        score = 0.0
        confidence = 0.45
        reason = "mixed_terms"

    event_type = "macro" if any(term in text for term in {"fed", "fomc", "cpi", "etf"}) else "market"
    urgency = "high" if any(term in text for term in {"panic", "pânico", "liquidation", "liquidação", "breaking"}) else "medium"

    return SentimentClassification(
        item_id=item.item_id,
        source_type=item.source_type,
        source_name=item.source_name,
        asset=item.asset,
        symbols=item.symbols,
        sentiment=sentiment,  # type: ignore[arg-type]
        score=score,
        confidence=confidence,
        event_type=event_type,  # type: ignore[arg-type]
        urgency=urgency,  # type: ignore[arg-type]
        time_horizon=item.metadata.get("time_horizon", item.metadata.get("timeframe", "unknown")),
        text_hash=item.text_hash,
        reason=reason,
        created_at=item.created_at,
        processed_at=datetime.now(timezone.utc),
        metadata=item.metadata,
    )


def run_sentiment_orchestrator(
    *,
    raw_items: list[RawSentimentItem | dict[str, Any]],
    asset: str = "BTCUSDT",
    timeframe: str = "5m",
    previous_score: float | None = None,
) -> SentimentOrchestratorReport:
    preprocess_config = PreprocessConfig(target_asset=asset)
    preprocess = preprocess_sentiment_items(raw_items, config=preprocess_config)

    clean_items = [
        CleanSentimentItem.model_validate(item)
        for item in preprocess.items
    ]

    classified = [classify_text(item) for item in clean_items]
    weighted = apply_source_weights(classified)

    sentiment_index = build_sentiment_index(
        items=weighted,
        asset=asset,
        timeframe=timeframe,
        previous_score=previous_score,
    )
    fear_greed = build_fear_greed_report(sentiment_index=sentiment_index)

    return SentimentOrchestratorReport(
        asset=asset,
        timeframe=timeframe,
        raw_items_count=len(raw_items),
        clean_items_count=len(clean_items),
        classified_items_count=len(weighted),
        sentiment_index=sentiment_index.model_dump(mode="json"),
        fear_greed=fear_greed.model_dump(mode="json"),
        classifications=[item.model_dump(mode="json") for item in weighted],
        preprocess=preprocess.model_dump(mode="json"),
    )


def export_sentiment_orchestrator_report(
    report: SentimentOrchestratorReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "sentiment_orchestrator_latest",
) -> Path:
    path = Path(output_dir or os.getenv("SENTIMENT_OUTPUT_DIR", "artifacts/sentiment"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def build_demo_raw_items() -> list[RawSentimentItem]:
    return [
        RawSentimentItem(
            item_id="demo_x_1",
            source_type="x",
            source_name="x_demo",
            text="BTC breakout with strong buy pressure 🚀",
            symbols=["BTCUSDT"],
            metadata={"verified_author": False},
        ),
        RawSentimentItem(
            item_id="demo_news_1",
            source_type="news",
            source_name="tier1_news_demo",
            text="Bitcoin ETF inflow supports bullish market sentiment",
            symbols=["BTCUSDT"],
            metadata={"source_tier": "tier1"},
        ),
        RawSentimentItem(
            item_id="demo_reddit_1",
            source_type="reddit",
            source_name="reddit_demo",
            text="BTC price may face resistance but support held",
            symbols=["BTCUSDT"],
        ),
    ]