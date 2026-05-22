from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from data.sentiment_feature_store import load_sentiment_feature_rows
from sentiment.sentiment_schema import SentimentFeatureRow


load_dotenv()


class SentimentDashboardSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sentiment_dashboard"
    latest: dict[str, Any] | None = None
    history_count: int = 0
    series: list[dict[str, Any]] = Field(default_factory=list)
    panels: dict[str, Any] = Field(default_factory=dict)


def load_sentiment_dashboard_rows(path: str | Path | None = None) -> list[SentimentFeatureRow]:
    resolved_path = path or os.getenv("SENTIMENT_DASHBOARD_FEATURE_FILE", "artifacts/sentiment/sentiment_features.jsonl")
    return load_sentiment_feature_rows(resolved_path)


def build_sentiment_dashboard_snapshot(
    *,
    rows: list[SentimentFeatureRow | dict[str, Any]] | None = None,
    max_points: int = 100,
) -> SentimentDashboardSnapshot:
    parsed_rows = [
        row if isinstance(row, SentimentFeatureRow) else SentimentFeatureRow.model_validate(row)
        for row in (rows if rows is not None else load_sentiment_dashboard_rows())
    ]

    limited = parsed_rows[-max_points:]
    latest = limited[-1] if limited else None

    series = [
        {
            "timestamp": row.timestamp.isoformat(),
            "btc_sentiment_index": row.btc_sentiment_index,
            "fear_greed_value": row.fear_greed_value,
            "sentiment_confidence": row.sentiment_confidence,
            "panic_score": row.panic_score,
            "euphoria_score": row.euphoria_score,
            "items_count": row.items_count,
        }
        for row in limited
    ]

    panels = {
        "sentiment_index": latest.btc_sentiment_index if latest else None,
        "fear_greed": latest.fear_greed_label if latest else None,
        "confidence": latest.sentiment_confidence if latest else None,
        "panic_score": latest.panic_score if latest else None,
        "euphoria_score": latest.euphoria_score if latest else None,
        "items_count": latest.items_count if latest else 0,
    }

    return SentimentDashboardSnapshot(
        latest=latest.model_dump(mode="json") if latest else None,
        history_count=len(parsed_rows),
        series=series,
        panels=panels,
    )


def render_sentiment_dashboard_html(snapshot: SentimentDashboardSnapshot) -> str:
    panels = snapshot.panels

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>BTC Sentiment Dashboard</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      background: #0f172a;
      color: #e5e7eb;
      margin: 0;
      padding: 24px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(180px, 1fr));
      gap: 16px;
    }}
    .card {{
      background: #111827;
      border: 1px solid #1f2937;
      border-radius: 16px;
      padding: 18px;
    }}
    .label {{
      color: #94a3b8;
      font-size: 13px;
    }}
    .value {{
      font-size: 28px;
      font-weight: 700;
      margin-top: 8px;
    }}
    pre {{
      background: #020617;
      padding: 16px;
      border-radius: 12px;
      overflow: auto;
    }}
  </style>
</head>
<body>
  <h1>BTC Sentiment Dashboard</h1>
  <div class="grid">
    <div class="card"><div class="label">Sentiment Index</div><div class="value">{panels.get("sentiment_index")}</div></div>
    <div class="card"><div class="label">Fear & Greed</div><div class="value">{panels.get("fear_greed")}</div></div>
    <div class="card"><div class="label">Confidence</div><div class="value">{panels.get("confidence")}</div></div>
    <div class="card"><div class="label">Panic Score</div><div class="value">{panels.get("panic_score")}</div></div>
    <div class="card"><div class="label">Euphoria Score</div><div class="value">{panels.get("euphoria_score")}</div></div>
    <div class="card"><div class="label">Items</div><div class="value">{panels.get("items_count")}</div></div>
  </div>
  <h2>Snapshot JSON</h2>
  <pre>{json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2)}</pre>
</body>
</html>
"""


def export_sentiment_dashboard_snapshot(
    snapshot: SentimentDashboardSnapshot,
    *,
    output_dir: str | Path | None = None,
    name: str = "sentiment_dashboard_latest",
) -> dict[str, Path]:
    path = Path(output_dir or os.getenv("SENTIMENT_DASHBOARD_OUTPUT_DIR", "artifacts/sentiment"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")

    json_path = path / f"{safe_name}.json"
    html_path = path / f"{safe_name}.html"

    json_path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    html_path.write_text(
        render_sentiment_dashboard_html(snapshot),
        encoding="utf-8",
    )

    return {
        "json": json_path,
        "html": html_path,
    }