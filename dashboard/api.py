"""
Dashboard local API.

Responsabilidades:
- Expor endpoints JSON locais.
- Servir uma página HTML simples inicial.
- Manter lógica de dados fora da camada HTTP.

Implementado com biblioteca padrão para evitar dependência obrigatória
de FastAPI/Flask nesta fase.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from dashboard.config import DashboardConfig, dashboard_config_to_dict, load_dashboard_config
from dashboard.metrics_builder import build_dashboard_summary
from dashboard.schemas import HealthStatus
from dashboard.templates import render_dashboard_html
from dashboard.theme_loader import load_theme_for_config


def json_response(payload: dict[str, Any], status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"


def html_response(payload: str, status: int = 200) -> tuple[int, bytes, str]:
    return status, payload.encode("utf-8"), "text/html; charset=utf-8"


def build_index_html(config: DashboardConfig) -> str:
    return render_dashboard_html(config)


def route_dashboard_request(
    path: str,
    *,
    config: DashboardConfig | None = None,
) -> tuple[int, bytes, str]:
    resolved_config = config or load_dashboard_config()

    clean_path = path.split("?", 1)[0].rstrip("/") or "/"

    if clean_path == "/":
        return html_response(build_index_html(resolved_config))

    if clean_path == "/health":
        return json_response(
            HealthStatus(status="ok").model_dump(mode="json")
        )

    if clean_path == "/dashboard/config":
        return json_response(dashboard_config_to_dict(resolved_config))

    if clean_path == "/dashboard/theme":
        return json_response(load_theme_for_config(resolved_config))

    summary = build_dashboard_summary(resolved_config)
    summary_payload = summary.model_dump(mode="json")

    if clean_path == "/dashboard/summary":
        return json_response(summary_payload)

    if clean_path == "/dashboard/paper-trading":
        return json_response(summary_payload["paper_trading"])

    if clean_path == "/dashboard/full-backtest":
        return json_response(summary_payload["full_backtest"])

    if clean_path == "/dashboard/calibration":
        return json_response(summary_payload["calibration"])

    if clean_path == "/dashboard/latest-trades":
        return json_response({"trades": summary_payload["recent_trades"]})

    return json_response(
        {
            "error": "not_found",
            "path": clean_path,
        },
        status=404,
    )


class DashboardRequestHandler(BaseHTTPRequestHandler):
    config: DashboardConfig = load_dashboard_config()

    def do_GET(self) -> None:
        status, body, content_type = route_dashboard_request(
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


def run_dashboard_server(config: DashboardConfig | None = None) -> None:
    resolved_config = config or load_dashboard_config()

    DashboardRequestHandler.config = resolved_config

    server = ThreadingHTTPServer(
        (resolved_config.host, resolved_config.port),
        DashboardRequestHandler,
    )

    print(f"Dashboard running at http://{resolved_config.host}:{resolved_config.port}")
    server.serve_forever()