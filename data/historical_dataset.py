"""
Historical dataset builder for Binance Futures.

Responsabilidades:
- Transformar resultados de backtest em linhas de dataset.
- Achatar features importantes.
- Criar split temporal train/validation/test.
- Exportar dataset em JSONL.

Este módulo NÃO treina modelos.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


DatasetSplit = Literal["train", "validation", "test"]


class DatasetRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: Any | None = None

    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str
    side: str

    target: int | None
    outcome: str | None

    entry_price: float | None = None
    exit_price: float | None = None

    net_pnl_usd: float | None = None
    gross_pnl_usd: float | None = None

    tech_score: float | None = None
    microstructure_score: float | None = None
    onchain_score: float | None = None
    sentiment_score: float | None = None
    combined_score: float | None = None

    binance_spread_pct: float | None = None
    binance_liquidity_usd: float | None = None

    funding_rate: float | None = None
    open_interest: float | None = None
    mark_price: float | None = None
    index_price: float | None = None

    features: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_raw_features(backtest_trade: dict[str, Any]) -> dict[str, Any]:
    signal = backtest_trade.get("signal") or {}

    raw_features = signal.get("raw_features")

    if isinstance(raw_features, dict):
        return raw_features

    return {}


def build_dataset_row_from_backtest_trade(backtest_trade: dict[str, Any]) -> DatasetRow | None:
    if not backtest_trade.get("executed"):
        return None

    simulation = backtest_trade.get("simulation") or {}
    pnl = backtest_trade.get("pnl") or simulation.get("pnl") or {}
    label = simulation.get("label") or {}
    raw_features = extract_raw_features(backtest_trade)

    target = simulation.get("target")

    if target is None:
        target = label.get("target")

    side = simulation.get("side") or backtest_trade.get("signal", {}).get("direction")

    return DatasetRow(
        timestamp=backtest_trade.get("timestamp"),
        venue=backtest_trade.get("venue") or "binance_futures",
        symbol=backtest_trade.get("symbol") or "BTCUSDT",
        timeframe=backtest_trade.get("timeframe") or raw_features.get("timeframe") or "5m",
        side=str(side),
        target=target,
        outcome=simulation.get("outcome") or label.get("outcome"),
        entry_price=safe_float(simulation.get("entry_price_filled")),
        exit_price=safe_float(simulation.get("exit_price_filled")),
        net_pnl_usd=safe_float(pnl.get("net_pnl_usd")),
        gross_pnl_usd=safe_float(pnl.get("gross_pnl_usd")),
        tech_score=safe_float(raw_features.get("tech_score")),
        microstructure_score=safe_float(raw_features.get("microstructure_score")),
        onchain_score=safe_float(raw_features.get("onchain_score")),
        sentiment_score=safe_float(raw_features.get("sentiment_score")),
        combined_score=safe_float(raw_features.get("combined_score")),
        binance_spread_pct=safe_float(raw_features.get("binance_spread_pct")),
        binance_liquidity_usd=safe_float(raw_features.get("binance_liquidity_usd")),
        funding_rate=safe_float(raw_features.get("funding_rate")),
        open_interest=safe_float(raw_features.get("open_interest")),
        mark_price=safe_float(raw_features.get("mark_price")),
        index_price=safe_float(raw_features.get("index_price")),
        features=raw_features,
        raw=backtest_trade,
    )


def build_dataset_from_backtest_report(report: dict[str, Any]) -> list[DatasetRow]:
    trades = report.get("trades") or []

    rows: list[DatasetRow] = []

    for trade in trades:
        row = build_dataset_row_from_backtest_trade(trade)

        if row is not None:
            rows.append(row)

    return rows


def sort_rows_temporally(rows: list[DatasetRow]) -> list[DatasetRow]:
    return sorted(rows, key=lambda row: str(row.timestamp or ""))


def temporal_split(
    rows: list[DatasetRow],
    *,
    train_ratio: float | None = None,
    validation_ratio: float | None = None,
    test_ratio: float | None = None,
) -> dict[DatasetSplit, list[DatasetRow]]:
    train = train_ratio if train_ratio is not None else float(os.getenv("HISTORICAL_DATASET_TRAIN_RATIO", "0.70"))
    validation = validation_ratio if validation_ratio is not None else float(os.getenv("HISTORICAL_DATASET_VALIDATION_RATIO", "0.15"))
    test = test_ratio if test_ratio is not None else float(os.getenv("HISTORICAL_DATASET_TEST_RATIO", "0.15"))

    total_ratio = train + validation + test

    if total_ratio <= 0:
        raise ValueError("soma dos ratios precisa ser maior que zero")

    train = train / total_ratio
    validation = validation / total_ratio

    sorted_rows = sort_rows_temporally(rows)

    n = len(sorted_rows)
    train_end = int(n * train)
    validation_end = train_end + int(n * validation)

    return {
        "train": sorted_rows[:train_end],
        "validation": sorted_rows[train_end:validation_end],
        "test": sorted_rows[validation_end:],
    }


def rows_to_dicts(rows: list[DatasetRow]) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in rows]


def export_jsonl(rows: list[DatasetRow], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row.model_dump(mode="json"), ensure_ascii=False))
            file.write("\n")

    return output_path


def load_jsonl(path: str | Path) -> list[DatasetRow]:
    input_path = Path(path)
    rows: list[DatasetRow] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            rows.append(DatasetRow.model_validate(json.loads(line)))

    return rows