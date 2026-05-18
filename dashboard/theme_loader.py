from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dashboard.config import DashboardConfig


DEFAULT_THEME = {
    "name": "professional",
    "background": "#0f172a",
    "surface": "#1e293b",
    "surface_alt": "#111827",
    "border": "#334155",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "good": "#22c55e",
    "bad": "#ef4444",
    "neutral": "#e2e8f0",
    "accent": "#38bdf8",
    "font_family": "Arial, sans-serif",
    "card_radius": "16px",
}


def theme_path(theme_name: str) -> Path:
    return Path("dashboard/themes") / f"{theme_name}.json"


def load_theme(theme_name: str | None = None) -> dict[str, Any]:
    selected = theme_name or "professional"
    path = theme_path(selected)

    if not path.exists():
        return dict(DEFAULT_THEME)

    payload = json.loads(path.read_text(encoding="utf-8"))

    theme = dict(DEFAULT_THEME)
    theme.update(payload)

    return theme


def load_theme_for_config(config: DashboardConfig) -> dict[str, Any]:
    return load_theme(config.theme)