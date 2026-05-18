"""
Dashboard data loader.

Responsabilidades:
- Ler relatórios gerados em artifacts/.
- Encontrar arquivos mais recentes.
- Carregar JSON e JSONL de forma segura.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def find_latest_file(
    directory: str | Path,
    pattern: str,
) -> Path | None:
    path = Path(directory)

    if not path.exists():
        return None

    files = [
        file
        for file in path.glob(pattern)
        if file.is_file()
    ]

    if not files:
        return None

    return max(files, key=lambda file: file.stat().st_mtime)


def load_json_file(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None

    file_path = Path(path)

    if not file_path.exists():
        return None

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_jsonl_file(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []

    file_path = Path(path)

    if not file_path.exists():
        return []

    rows: list[dict[str, Any]] = []

    with file_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            rows.append(json.loads(line))

    return rows


def load_latest_paper_trading_report(directory: str | Path) -> tuple[dict[str, Any] | None, Path | None]:
    latest = find_latest_file(directory, "*_summary.json")

    return load_json_file(latest), latest


def load_latest_paper_trading_trades(directory: str | Path) -> tuple[list[dict[str, Any]], Path | None]:
    latest = find_latest_file(directory, "*_trades.jsonl")

    return load_jsonl_file(latest), latest


def load_latest_full_backtest_report(directory: str | Path) -> tuple[dict[str, Any] | None, Path | None]:
    latest = find_latest_file(directory, "*_summary.json")

    return load_json_file(latest), latest


def load_latest_full_backtest_trades(directory: str | Path) -> tuple[list[dict[str, Any]], Path | None]:
    latest = find_latest_file(directory, "*_trades.jsonl")

    return load_jsonl_file(latest), latest


def load_latest_calibration_report(directory: str | Path) -> tuple[dict[str, Any] | None, Path | None]:
    latest = find_latest_file(directory, "*.json")

    return load_json_file(latest), latest


def normalize_path(path: Path | None) -> str | None:
    if path is None:
        return None

    return str(path)