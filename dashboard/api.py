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


def json_response(payload: dict[str, Any], status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"


def html_response(payload: str, status: int = 200) -> tuple[int, bytes, str]:
    return status, payload.encode("utf-8"), "text/html; charset=utf-8"


def build_index_html(config: DashboardConfig) -> str:
    refresh_ms = config.refresh_seconds * 1000

    return f"""
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <title>BTC Binance Futures Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
    }}
    header {{
      padding: 24px;
      background: #111827;
      border-bottom: 1px solid #334155;
    }}
    main {{
      padding: 24px;
      display: grid;
      gap: 16px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 16px;
    }}
    .label {{
      color: #94a3b8;
      font-size: 14px;
    }}
    .value {{
      font-size: 26px;
      font-weight: 700;
      margin-top: 8px;
    }}
    .good {{ color: #22c55e; }}
    .bad {{ color: #ef4444; }}
    .neutral {{ color: #e2e8f0; }}
    pre {{
      background: #020617;
      padding: 16px;
      border-radius: 12px;
      overflow: auto;
    }}
  </style>
</head>
<body>
  <header>
    <h1>BTC Binance Futures Dashboard</h1>
    <p>Atualização a cada {config.refresh_seconds}s — tema: {config.theme}</p>
  </header>

  <main>
    <section>
      <h2>Resumo</h2>
      <div id="cards" class="grid"></div>
    </section>

    <section>
      <h2>Últimos trades</h2>
      <pre id="trades">Carregando...</pre>
    </section>
  </main>

  <script>
    async function refresh() {{
      const response = await fetch('/dashboard/summary');
      const data = await response.json();

      const cards = [];
      for (const section of ['paper_trading', 'full_backtest', 'calibration']) {{
        const payload = data[section];
        if (!payload || !payload.cards) continue;
        cards.push(...payload.cards);
      }}

      document.getElementById('cards').innerHTML = cards.map(card => `
        <div class="card">
          <div class="label">${{card.label}}</div>
          <div class="value ${{card.status}}">${{card.value ?? 'N/A'}} ${{card.unit ?? ''}}</div>
        </div>
      `).join('');

      document.getElementById('trades').textContent = JSON.stringify(data.recent_trades || [], null, 2);
    }}

    refresh();
    setInterval(refresh, {refresh_ms});
  </script>
</body>
</html>
"""


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