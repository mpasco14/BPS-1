from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from observability.metrics_registry import MetricSample, MetricsSnapshot, normalize_metric_name


load_dotenv()


def prometheus_namespace() -> str:
    return normalize_metric_name(os.getenv("PROMETHEUS_NAMESPACE", "btc_bot"))


def escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def sanitize_label_name(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())

    if not sanitized:
        return "label"

    if sanitized[0].isdigit():
        sanitized = f"label_{sanitized}"

    return sanitized


def render_labels(labels: dict[str, Any]) -> str:
    if not labels:
        return ""

    parts = [
        f'{sanitize_label_name(str(key))}="{escape_label_value(str(value))}"'
        for key, value in sorted(labels.items())
    ]

    return "{" + ",".join(parts) + "}"


def render_prometheus_metric(
    metric: MetricSample | dict[str, Any],
    *,
    namespace: str | None = None,
) -> str:
    parsed = metric if isinstance(metric, MetricSample) else MetricSample.model_validate(metric)
    ns = normalize_metric_name(namespace or prometheus_namespace())
    name = normalize_metric_name(f"{ns}_{parsed.name}")
    labels = render_labels(parsed.labels)

    help_line = f"# HELP {name} {parsed.description or parsed.name}"
    type_line = f"# TYPE {name} {parsed.metric_type}"
    value_line = f"{name}{labels} {parsed.value}"

    return "\n".join([help_line, type_line, value_line])


def render_prometheus_text(
    snapshot: MetricsSnapshot | dict[str, Any],
    *,
    namespace: str | None = None,
) -> str:
    parsed = snapshot if isinstance(snapshot, MetricsSnapshot) else MetricsSnapshot.model_validate(snapshot)

    blocks = [
        render_prometheus_metric(metric, namespace=namespace)
        for metric in parsed.metrics
    ]

    return "\n\n".join(blocks) + ("\n" if blocks else "")


def export_prometheus_metrics(
    snapshot: MetricsSnapshot | dict[str, Any],
    *,
    path: str | Path | None = None,
    namespace: str | None = None,
) -> Path:
    output_path = Path(path or os.getenv("PROMETHEUS_METRICS_FILE", "artifacts/observability/prometheus_metrics.prom"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        render_prometheus_text(snapshot, namespace=namespace),
        encoding="utf-8",
    )

    return output_path