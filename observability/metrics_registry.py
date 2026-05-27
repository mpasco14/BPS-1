from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


MetricType = Literal["gauge", "counter", "histogram"]


class MetricsRegistryConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/observability")
    snapshot_file: Path = Path("artifacts/observability/metrics_snapshot.json")


class MetricSample(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    value: float
    metric_type: MetricType = "gauge"

    labels: dict[str, str] = Field(default_factory=dict)
    unit: str | None = None
    description: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MetricsSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "metrics_registry"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    metrics_count: int
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_metrics_registry_config() -> MetricsRegistryConfig:
    return MetricsRegistryConfig(
        output_dir=Path(os.getenv("METRICS_REGISTRY_OUTPUT_DIR", "artifacts/observability")),
        snapshot_file=Path(os.getenv("METRICS_REGISTRY_SNAPSHOT_FILE", "artifacts/observability/metrics_snapshot.json")),
    )


def normalize_metric_name(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_:]+", "_", name.strip())
    normalized = re.sub(r"_+", "_", normalized)

    if not normalized:
        return "unknown_metric"

    if normalized[0].isdigit():
        normalized = f"metric_{normalized}"

    return normalized.lower()


def metric_sample(
    *,
    name: str,
    value: float | int | bool,
    metric_type: MetricType = "gauge",
    labels: dict[str, Any] | None = None,
    unit: str | None = None,
    description: str | None = None,
) -> MetricSample:
    numeric_value = 1.0 if value is True else 0.0 if value is False else float(value)

    normalized_labels = {
        str(key): str(label_value)
        for key, label_value in (labels or {}).items()
        if label_value is not None
    }

    return MetricSample(
        name=normalize_metric_name(name),
        value=numeric_value,
        metric_type=metric_type,
        labels=normalized_labels,
        unit=unit,
        description=description,
    )


def build_metrics_snapshot(
    *,
    metrics: list[MetricSample | dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> MetricsSnapshot:
    parsed = [
        item if isinstance(item, MetricSample) else MetricSample.model_validate(item)
        for item in metrics
    ]

    return MetricsSnapshot(
        metrics_count=len(parsed),
        metrics=[item.model_dump(mode="json") for item in parsed],
        metadata=metadata or {},
    )


def metric_value(snapshot: MetricsSnapshot | dict[str, Any], name: str) -> float | None:
    parsed = snapshot if isinstance(snapshot, MetricsSnapshot) else MetricsSnapshot.model_validate(snapshot)
    target = normalize_metric_name(name)

    for item in parsed.metrics:
        if item.get("name") == target:
            return float(item.get("value", 0))

    return None


def metrics_from_report(
    *,
    report: dict[str, Any],
    prefix: str,
    labels: dict[str, Any] | None = None,
    include_keys: list[str] | None = None,
) -> list[MetricSample]:
    samples: list[MetricSample] = []
    keys = include_keys or list(report.keys())

    for key in keys:
        value = report.get(key)

        if isinstance(value, bool):
            samples.append(metric_sample(name=f"{prefix}_{key}", value=value, labels=labels))
        elif isinstance(value, int | float):
            samples.append(metric_sample(name=f"{prefix}_{key}", value=value, labels=labels))

    return samples


def build_core_metrics_snapshot(
    *,
    live_performance: dict[str, Any] | None = None,
    live_risk_audit: dict[str, Any] | None = None,
    drift_report: dict[str, Any] | None = None,
    production_guard: dict[str, Any] | None = None,
    strategy_health: dict[str, Any] | None = None,
    sentiment: dict[str, Any] | None = None,
) -> MetricsSnapshot:
    metrics: list[MetricSample] = []

    if live_performance:
        metrics.extend(
            metrics_from_report(
                report=live_performance,
                prefix="live_performance",
                include_keys=[
                    "passed",
                    "submitted_count",
                    "filled_count",
                    "canceled_count",
                    "rejected_count",
                    "fill_rate",
                    "cancel_rate",
                    "rejection_rate",
                    "net_pnl_usd",
                    "max_drawdown_usd",
                    "average_slippage_pct",
                    "average_latency_ms",
                ],
            )
        )

    if live_risk_audit:
        metrics.extend(
            metrics_from_report(
                report=live_risk_audit,
                prefix="live_risk_audit",
                include_keys=[
                    "passed",
                    "findings_count",
                    "critical_findings_count",
                    "blocking_findings_count",
                    "max_margin_seen_usd",
                    "max_notional_seen_usd",
                    "realized_daily_pnl_usd",
                ],
            )
        )

    if drift_report:
        metrics.extend(
            metrics_from_report(
                report=drift_report,
                prefix="live_drift",
                include_keys=[
                    "passed",
                    "samples_count",
                    "labeled_samples_count",
                    "brier_score",
                    "expected_calibration_error",
                    "ood_rate",
                    "confidence_gap",
                    "high_confidence_win_rate",
                ],
            )
        )

    if production_guard:
        metrics.extend(
            metrics_from_report(
                report=production_guard,
                prefix="production_guard",
                include_keys=[
                    "passed",
                    "checks_count",
                    "fail_count",
                    "blocking_fail_count",
                    "warn_count",
                ],
            )
        )

    if strategy_health:
        metrics.extend(
            metrics_from_report(
                report=strategy_health,
                prefix="strategy_health",
                include_keys=[
                    "passed",
                    "health_score",
                ],
            )
        )

    if sentiment:
        metrics.extend(
            metrics_from_report(
                report=sentiment,
                prefix="sentiment",
                include_keys=[
                    "btc_sentiment_index",
                    "fear_greed_value",
                    "panic_score",
                    "euphoria_score",
                    "sentiment_confidence",
                    "items_count",
                ],
            )
        )

    return build_metrics_snapshot(metrics=metrics)


def export_metrics_snapshot(
    snapshot: MetricsSnapshot,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_metrics_registry_config()
    output_path = Path(path or config.snapshot_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def load_metrics_snapshot(path: str | Path | None = None) -> MetricsSnapshot | None:
    config = load_metrics_registry_config()
    input_path = Path(path or config.snapshot_file)

    if not input_path.exists():
        return None

    return MetricsSnapshot.model_validate(json.loads(input_path.read_text(encoding="utf-8")))