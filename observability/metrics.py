"""
Prometheus-compatible metrics endpoint.

Responsabilidades:
- Converter métricas do dashboard em formato Prometheus.
- Expor /metrics e /health via HTTP server simples.
- Evitar dependência obrigatória de prometheus_client nesta fase.
"""

from __future__ import annotations

import json
import math
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from dashboard.config import DashboardConfig, load_dashboard_config
from dashboard.metrics_builder import build_dashboard_summary
from observability.health import build_system_health


load_dotenv()


class MetricSample(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    value: float
    metric_type: str = "gauge"
    help_text: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def metric_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    normalized = re.sub(r"_+", "_", normalized).strip("_").lower()

    if not normalized:
        normalized = "unknown_metric"

    if normalized[0].isdigit():
        normalized = f"metric_{normalized}"

    return normalized


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(parsed) or math.isinf(parsed):
        return None

    return parsed


def escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""

    parts = [
        f'{metric_name(key)}="{escape_label_value(str(value))}"'
        for key, value in labels.items()
    ]

    return "{" + ",".join(parts) + "}"


def render_prometheus_text(samples: list[MetricSample]) -> str:
    lines: list[str] = []
    emitted_headers: set[str] = set()

    for sample in samples:
        name = metric_name(sample.name)

        if name not in emitted_headers:
            help_text = sample.help_text or name
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {sample.metric_type}")
            emitted_headers.add(name)

        labels = render_labels(sample.labels)
        lines.append(f"{name}{labels} {sample.value}")

    return "\n".join(lines) + "\n"


def dashboard_card_samples(config: DashboardConfig) -> list[MetricSample]:
    if not env_bool("OBSERVABILITY_INCLUDE_DASHBOARD_METRICS", True):
        return []

    summary = build_dashboard_summary(config)
    payload = summary.model_dump(mode="json")

    samples: list[MetricSample] = []

    for section_name in ["paper_trading", "full_backtest", "calibration"]:
        section = payload.get(section_name) or {}
        cards = section.get("cards") or []

        for card in cards:
            value = safe_float(card.get("value"))

            if value is None:
                continue

            key = metric_name(str(card.get("key") or card.get("label") or "unknown"))
            name = f"btc_bot_{key}"

            samples.append(
                MetricSample(
                    name=name,
                    value=value,
                    help_text=str(card.get("label") or key),
                    labels={
                        "section": section_name,
                        "status": str(card.get("status") or "neutral"),
                    },
                )
            )

    samples.append(
        MetricSample(
            name="btc_bot_recent_trades_total",
            value=float(len(payload.get("recent_trades") or [])),
            help_text="Recent trades loaded by dashboard",
        )
    )

    return samples


def health_samples(config: DashboardConfig) -> list[MetricSample]:
    if not env_bool("OBSERVABILITY_INCLUDE_HEALTH_METRICS", True):
        return []

    health = build_system_health(config)

    samples = [
        MetricSample(
            name="btc_bot_up",
            value=1.0 if health.status == "ok" else 0.0,
            help_text="Bot health status",
        )
    ]

    for check in health.checks:
        status = str(check.get("status"))

        value = 1.0 if status == "ok" else 0.0

        samples.append(
            MetricSample(
                name="btc_bot_component_up",
                value=value,
                help_text="Component health status",
                labels={
                    "component": str(check.get("name")),
                    "status": status,
                },
            )
        )

    return samples


def build_observability_samples(config: DashboardConfig | None = None) -> list[MetricSample]:
    resolved_config = config or load_dashboard_config()

    samples: list[MetricSample] = []

    samples.extend(health_samples(resolved_config))
    samples.extend(dashboard_card_samples(resolved_config))

    return samples


def build_metrics_text(config: DashboardConfig | None = None) -> str:
    return render_prometheus_text(
        build_observability_samples(config)
    )


def text_response(payload: str, status: int = 200, content_type: str = "text/plain; version=0.0.4") -> tuple[int, bytes, str]:
    return status, payload.encode("utf-8"), content_type


def json_response(payload: dict[str, Any], status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"


def route_observability_request(
    path: str,
    *,
    config: DashboardConfig | None = None,
) -> tuple[int, bytes, str]:
    resolved_config = config or load_dashboard_config()

    clean_path = path.split("?", 1)[0].rstrip("/") or "/"

    metrics_path = os.getenv("OBSERVABILITY_METRICS_PATH", "/metrics")
    health_path = os.getenv("OBSERVABILITY_HEALTH_PATH", "/health")

    if clean_path == "/":
        return json_response(
            {
                "service": os.getenv("OBSERVABILITY_SERVICE_NAME", "btc-binance-bot"),
                "endpoints": [metrics_path, health_path],
            }
        )

    if clean_path == metrics_path:
        return text_response(build_metrics_text(resolved_config))

    if clean_path == health_path:
        return json_response(
            build_system_health(resolved_config).model_dump(mode="json")
        )

    return json_response(
        {
            "error": "not_found",
            "path": clean_path,
        },
        status=404,
    )


class ObservabilityRequestHandler(BaseHTTPRequestHandler):
    config: DashboardConfig = load_dashboard_config()

    def do_GET(self) -> None:
        status, body, content_type = route_observability_request(
            self.path,
            config=self.config,
        )

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_observability_server(
    *,
    host: str | None = None,
    port: int | None = None,
    config: DashboardConfig | None = None,
) -> None:
    resolved_host = host or os.getenv("OBSERVABILITY_HOST", "127.0.0.1")
    resolved_port = port or env_int("OBSERVABILITY_PORT", 8001)

    resolved_config = config or load_dashboard_config()
    ObservabilityRequestHandler.config = resolved_config

    server = ThreadingHTTPServer(
        (resolved_host, resolved_port),
        ObservabilityRequestHandler,
    )

    print(f"Observability server running at http://{resolved_host}:{resolved_port}")
    print(f"Metrics: http://{resolved_host}:{resolved_port}{os.getenv('OBSERVABILITY_METRICS_PATH', '/metrics')}")
    print(f"Health:  http://{resolved_host}:{resolved_port}{os.getenv('OBSERVABILITY_HEALTH_PATH', '/health')}")

    server.serve_forever()