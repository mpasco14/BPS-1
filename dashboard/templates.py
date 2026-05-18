from __future__ import annotations

from html import escape
from typing import Any

from dashboard.config import DashboardConfig
from dashboard.theme_loader import load_theme_for_config


def css_vars(theme: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"--bg: {theme['background']};",
            f"--surface: {theme['surface']};",
            f"--surface-alt: {theme['surface_alt']};",
            f"--border: {theme['border']};",
            f"--text: {theme['text']};",
            f"--muted: {theme['muted']};",
            f"--good: {theme['good']};",
            f"--bad: {theme['bad']};",
            f"--neutral: {theme['neutral']};",
            f"--accent: {theme['accent']};",
            f"--font-family: {theme['font_family']};",
            f"--card-radius: {theme['card_radius']};",
        ]
    )


def render_dashboard_html(config: DashboardConfig) -> str:
    theme = load_theme_for_config(config)
    refresh_ms = config.refresh_seconds * 1000
    theme_name = escape(str(theme.get("name", config.theme)))

    return f"""
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <title>BTC Binance Futures Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {{
      {css_vars(theme)}
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      font-family: var(--font-family);
      background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.10), transparent 30%), var(--bg);
      color: var(--text);
    }}

    header {{
      padding: 28px;
      background: linear-gradient(135deg, var(--surface-alt), var(--surface));
      border-bottom: 1px solid var(--border);
    }}

    header h1 {{
      margin: 0;
      font-size: 28px;
    }}

    header p {{
      margin: 8px 0 0 0;
      color: var(--muted);
    }}

    main {{
      padding: 24px;
      display: grid;
      gap: 22px;
    }}

    .section-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}

    .pill {{
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 6px 12px;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.03);
      font-size: 13px;
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}

    .card {{
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01)), var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--card-radius);
      padding: 18px;
      box-shadow: 0 18px 45px rgba(0, 0, 0, 0.20);
    }}

    .label {{
      color: var(--muted);
      font-size: 14px;
    }}

    .value {{
      font-size: 26px;
      font-weight: 800;
      margin-top: 8px;
    }}

    .good {{ color: var(--good); }}
    .bad {{ color: var(--bad); }}
    .neutral {{ color: var(--neutral); }}

    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--card-radius);
      overflow: hidden;
    }}

    th, td {{
      padding: 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      font-size: 14px;
    }}

    th {{
      color: var(--muted);
      background: var(--surface-alt);
    }}

    tr:last-child td {{
      border-bottom: none;
    }}

    pre {{
      background: #020617;
      padding: 16px;
      border-radius: var(--card-radius);
      overflow: auto;
      border: 1px solid var(--border);
    }}

    .error {{
      color: var(--bad);
      padding: 16px;
      border: 1px solid var(--bad);
      border-radius: var(--card-radius);
      background: rgba(239, 68, 68, 0.08);
    }}
  </style>
</head>
<body>
  <header>
    <h1>BTC Binance Futures Dashboard</h1>
    <p>Dashboard local • tema: {theme_name} • atualização a cada {config.refresh_seconds}s</p>
  </header>

  <main>
    <section>
      <div class="section-header">
        <h2>Resumo operacional</h2>
        <span id="updated-at" class="pill">Carregando...</span>
      </div>
      <div id="cards" class="grid"></div>
    </section>

    <section>
      <div class="section-header">
        <h2>Últimos trades</h2>
        <span class="pill">paper + backtest</span>
      </div>
      <div id="trades"></div>
    </section>

    <section>
      <div class="section-header">
        <h2>Calibração</h2>
        <span class="pill">Brier / ECE</span>
      </div>
      <pre id="calibration">Carregando...</pre>
    </section>
  </main>

  <script>
    function formatValue(value) {{
      if (value === null || value === undefined) return "N/A";
      if (typeof value === "number") return Number(value.toFixed(6)).toString();
      return value;
    }}

    function renderCards(data) {{
      const cards = [];

      for (const section of ["paper_trading", "full_backtest", "calibration"]) {{
        const payload = data[section];
        if (!payload || !payload.cards) continue;
        cards.push(...payload.cards);
      }}

      document.getElementById("cards").innerHTML = cards.map(card => `
        <div class="card">
          <div class="label">${{card.label}}</div>
          <div class="value ${{card.status}}">${{formatValue(card.value)}} ${{card.unit ?? ""}}</div>
        </div>
      `).join("");
    }}

    function renderTrades(data) {{
      const trades = data.recent_trades || [];

      if (!trades.length) {{
        document.getElementById("trades").innerHTML = "<div class='card'>Nenhum trade encontrado.</div>";
        return;
      }}

      document.getElementById("trades").innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Símbolo</th>
              <th>TF</th>
              <th>Lado</th>
              <th>Resultado</th>
              <th>PnL</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${{trades.map(trade => `
              <tr>
                <td>${{trade.timestamp ?? ""}}</td>
                <td>${{trade.symbol ?? ""}}</td>
                <td>${{trade.timeframe ?? ""}}</td>
                <td>${{trade.side ?? ""}}</td>
                <td>${{trade.outcome ?? ""}}</td>
                <td>${{formatValue(trade.net_pnl_usd)}}</td>
                <td>${{trade.blocked ? "blocked" : "routed"}}</td>
              </tr>
            `).join("")}}
          </tbody>
        </table>
      `;
    }}

    async function refresh() {{
      try {{
        const response = await fetch("/dashboard/summary");
        const data = await response.json();

        document.getElementById("updated-at").textContent = `Atualizado: ${{data.generated_at}}`;

        renderCards(data);
        renderTrades(data);

        document.getElementById("calibration").textContent = JSON.stringify(data.calibration || {{}}, null, 2);
      }} catch (error) {{
        document.getElementById("cards").innerHTML = `<div class="error">Erro ao carregar dashboard: ${{error}}</div>`;
      }}
    }}

    refresh();
    setInterval(refresh, {refresh_ms});
  </script>
</body>
</html>
"""


def render_dashboard_html_preview(config: DashboardConfig) -> str:
    return render_dashboard_html(config)