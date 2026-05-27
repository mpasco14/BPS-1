from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from observability.metrics_registry import MetricSample, MetricsSnapshot, normalize_metric_name


load_dotenv()


def panel_for_metric(
    *,
    metric_name: str,
    title: str,
    panel_id: int,
    x: int,
    y: int,
    w: int = 8,
    h: int = 6,
    namespace: str | None = None,
) -> dict[str, Any]:
    ns = normalize_metric_name(namespace or os.getenv("PROMETHEUS_NAMESPACE", "btc_bot"))
    normalized = normalize_metric_name(metric_name)
    prometheus_name = normalize_metric_name(f"{ns}_{normalized}")

    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [
            {
                "expr": prometheus_name,
                "legendFormat": normalized,
                "refId": "A",
            }
        ],
        "fieldConfig": {
            "defaults": {
                "unit": "short",
            },
            "overrides": [],
        },
        "options": {
            "legend": {
                "displayMode": "list",
                "placement": "bottom",
            }
        },
    }


def build_grafana_dashboard_config(
    *,
    snapshot: MetricsSnapshot | dict[str, Any] | None = None,
    title: str | None = None,
    namespace: str | None = None,
) -> dict[str, Any]:
    resolved_title = title or os.getenv("GRAFANA_DASHBOARD_TITLE", "BTC Binance Futures Bot")

    if snapshot is None:
        metric_names = [
            "live_performance_net_pnl_usd",
            "live_performance_fill_rate",
            "live_performance_rejection_rate",
            "live_risk_audit_critical_findings_count",
            "live_drift_ood_rate",
            "production_guard_blocking_fail_count",
            "strategy_health_health_score",
            "sentiment_btc_sentiment_index",
        ]
    else:
        parsed = snapshot if isinstance(snapshot, MetricsSnapshot) else MetricsSnapshot.model_validate(snapshot)
        metric_names = [MetricSample.model_validate(item).name for item in parsed.metrics[:12]]

    panels: list[dict[str, Any]] = []

    for index, metric_name in enumerate(metric_names, start=1):
        x = ((index - 1) % 3) * 8
        y = ((index - 1) // 3) * 6

        panels.append(
            panel_for_metric(
                metric_name=metric_name,
                title=metric_name.replace("_", " ").title(),
                panel_id=index,
                x=x,
                y=y,
                namespace=namespace,
            )
        )

    return {
        "title": resolved_title,
        "schemaVersion": 39,
        "version": 1,
        "refresh": "30s",
        "timezone": "browser",
        "tags": ["btc", "binance-futures", "trading-bot", "observability"],
        "panels": panels,
        "templating": {
            "list": []
        },
    }


def export_grafana_dashboard_config(
    dashboard: dict[str, Any],
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or os.getenv("GRAFANA_DASHBOARD_FILE", "artifacts/observability/grafana_dashboard.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path