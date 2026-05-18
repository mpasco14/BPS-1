"""
Full backtest validation for Binance Futures.

Responsabilidades:
- Rodar paper_trading_loop com custos realistas.
- Aplicar simulação de partial fills.
- Calcular ROI, Sharpe, max drawdown, hit rate, profit factor.
- Calcular PnL por timeframe e por direção.
- Exportar relatório auditável.

Este módulo NÃO executa ordens reais.
"""

from __future__ import annotations

import copy
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from execution.limit_order import SymbolTradingRules
from execution.paper_trading_loop import PaperTradingSessionReport, run_paper_trading_session
from risk.exposure import ExposureSnapshot
from risk.risk_manager import RiskProfile


load_dotenv()


class FullBacktestCostModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    taker_fee_rate: float = 0.0005
    maker_fee_rate: float = 0.0002
    spread_pct: float = 0.0002
    slippage_pct: float = 0.0005
    latency_ms: int = 200
    funding_cost_usd: float = 0.0
    partial_fill_ratio: float = 1.0


class FullBacktestMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_trades: int
    routed_orders: int
    blocked_orders: int

    roi_pct: float
    sharpe: float | None
    max_drawdown_pct: float

    hit_rate: float
    profit_factor: float | None

    net_pnl_usd: float
    gross_pnl_usd: float

    pnl_by_timeframe: dict[str, float] = Field(default_factory=dict)
    pnl_by_direction: dict[str, float] = Field(default_factory=dict)

    average_trade_pnl_usd: float | None = None
    average_win_usd: float | None = None
    average_loss_usd: float | None = None


class FullBacktestReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "full_backtest"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    cost_model: dict[str, Any]
    metrics: dict[str, Any]

    trades: list[dict[str, Any]] = Field(default_factory=list)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_full_backtest_cost_model() -> FullBacktestCostModel:
    return FullBacktestCostModel(
        taker_fee_rate=env_float("FULL_BACKTEST_BINANCE_TAKER_FEE_RATE", 0.0005),
        maker_fee_rate=env_float("FULL_BACKTEST_BINANCE_MAKER_FEE_RATE", 0.0002),
        spread_pct=env_float("FULL_BACKTEST_SPREAD_PCT", 0.0002),
        slippage_pct=env_float("FULL_BACKTEST_SLIPPAGE_PCT", 0.0005),
        latency_ms=env_int("FULL_BACKTEST_LATENCY_MS", 200),
        funding_cost_usd=env_float("FULL_BACKTEST_FUNDING_COST_USD", 0.0),
        partial_fill_ratio=env_float("FULL_BACKTEST_PARTIAL_FILL_RATIO", 1.0),
    )


def clamp_partial_fill_ratio(value: float) -> float:
    return max(0.0, min(1.0, value))


def scale_pnl_payload(pnl: dict[str, Any], ratio: float) -> dict[str, Any]:
    scaled = dict(pnl)

    for key in [
        "gross_pnl_usd",
        "net_pnl_usd",
        "fees_usd",
        "entry_fee_usd",
        "exit_fee_usd",
        "funding_cost_usd",
    ]:
        if key in scaled and isinstance(scaled[key], int | float):
            scaled[key] = scaled[key] * ratio

    if "is_win" in scaled:
        scaled["is_win"] = scaled.get("net_pnl_usd", 0.0) > 0

    return scaled


def apply_partial_fill_ratio_to_trades(
    trades: list[dict[str, Any]],
    *,
    partial_fill_ratio: float,
) -> list[dict[str, Any]]:
    ratio = clamp_partial_fill_ratio(partial_fill_ratio)
    adjusted: list[dict[str, Any]] = []

    for trade in trades:
        item = copy.deepcopy(trade)
        item["partial_fill_ratio"] = ratio

        pnl = item.get("pnl")

        if isinstance(pnl, dict):
            item["pnl"] = scale_pnl_payload(pnl, ratio)

        market_would_do = item.get("market_would_do")

        if isinstance(market_would_do, dict) and isinstance(market_would_do.get("pnl"), dict):
            market_would_do["pnl"] = scale_pnl_payload(market_would_do["pnl"], ratio)

        adjusted.append(item)

    return adjusted


def extract_net_pnls(trades: list[dict[str, Any]]) -> list[float]:
    pnls: list[float] = []

    for trade in trades:
        pnl = trade.get("pnl") or {}

        if isinstance(pnl, dict) and isinstance(pnl.get("net_pnl_usd"), int | float):
            pnls.append(float(pnl["net_pnl_usd"]))

    return pnls


def extract_gross_pnls(trades: list[dict[str, Any]]) -> list[float]:
    pnls: list[float] = []

    for trade in trades:
        pnl = trade.get("pnl") or {}

        if isinstance(pnl, dict) and isinstance(pnl.get("gross_pnl_usd"), int | float):
            pnls.append(float(pnl["gross_pnl_usd"]))

    return pnls


def calculate_equity_curve(
    *,
    initial_balance_usd: float,
    net_pnls: list[float],
) -> list[float]:
    equity = [initial_balance_usd]
    current = initial_balance_usd

    for pnl in net_pnls:
        current += pnl
        equity.append(current)

    return equity


def calculate_max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_drawdown = 0.0

    for value in equity_curve:
        peak = max(peak, value)

        if peak <= 0:
            continue

        drawdown = (peak - value) / peak
        max_drawdown = max(max_drawdown, drawdown)

    return max_drawdown


def calculate_trade_sharpe(
    *,
    net_pnls: list[float],
    initial_balance_usd: float,
) -> float | None:
    if len(net_pnls) < 2 or initial_balance_usd <= 0:
        return None

    returns = [pnl / initial_balance_usd for pnl in net_pnls]
    mean_return = statistics.mean(returns)
    std_return = statistics.pstdev(returns)

    if std_return == 0:
        return None

    return mean_return / std_return * math.sqrt(len(returns))


def calculate_profit_factor(net_pnls: list[float]) -> float | None:
    gross_profit = sum(pnl for pnl in net_pnls if pnl > 0)
    gross_loss = abs(sum(pnl for pnl in net_pnls if pnl < 0))

    if gross_loss == 0:
        return None if gross_profit == 0 else float("inf")

    return gross_profit / gross_loss


def calculate_grouped_pnl(
    trades: list[dict[str, Any]],
    *,
    group_key: str,
) -> dict[str, float]:
    grouped: dict[str, float] = {}

    for trade in trades:
        pnl = trade.get("pnl") or {}

        if not isinstance(pnl, dict):
            continue

        net = pnl.get("net_pnl_usd")

        if not isinstance(net, int | float):
            continue

        if group_key == "direction":
            signal = trade.get("signal") or {}
            key = str(signal.get("direction") or "UNKNOWN")
        else:
            key = str(trade.get(group_key) or "UNKNOWN")

        grouped[key] = grouped.get(key, 0.0) + float(net)

    return grouped


def calculate_full_backtest_metrics(
    *,
    trades: list[dict[str, Any]],
    initial_balance_usd: float,
    routed_orders: int,
    blocked_orders: int,
) -> FullBacktestMetrics:
    net_pnls = extract_net_pnls(trades)
    gross_pnls = extract_gross_pnls(trades)

    wins = [pnl for pnl in net_pnls if pnl > 0]
    losses = [pnl for pnl in net_pnls if pnl < 0]

    total_net = sum(net_pnls)
    total_gross = sum(gross_pnls)

    roi_pct = total_net / initial_balance_usd if initial_balance_usd > 0 else 0.0
    hit_rate = len(wins) / len(net_pnls) if net_pnls else 0.0

    equity_curve = calculate_equity_curve(
        initial_balance_usd=initial_balance_usd,
        net_pnls=net_pnls,
    )

    return FullBacktestMetrics(
        total_trades=len(net_pnls),
        routed_orders=routed_orders,
        blocked_orders=blocked_orders,
        roi_pct=roi_pct,
        sharpe=calculate_trade_sharpe(
            net_pnls=net_pnls,
            initial_balance_usd=initial_balance_usd,
        ),
        max_drawdown_pct=calculate_max_drawdown_pct(equity_curve),
        hit_rate=hit_rate,
        profit_factor=calculate_profit_factor(net_pnls),
        net_pnl_usd=total_net,
        gross_pnl_usd=total_gross,
        pnl_by_timeframe=calculate_grouped_pnl(trades, group_key="timeframe"),
        pnl_by_direction=calculate_grouped_pnl(trades, group_key="direction"),
        average_trade_pnl_usd=(total_net / len(net_pnls)) if net_pnls else None,
        average_win_usd=(sum(wins) / len(wins)) if wins else None,
        average_loss_usd=(sum(losses) / len(losses)) if losses else None,
    )


def run_full_backtest(
    *,
    feature_snapshots: list[dict[str, Any]],
    price_paths: dict[str, list[dict[str, Any]]],
    rules: SymbolTradingRules,
    profile: RiskProfile | None = None,
    exposure_snapshot: ExposureSnapshot | None = None,
    session_name: str = "full_backtest",
    initial_balance_usd: float | None = None,
    cost_model: FullBacktestCostModel | None = None,
) -> FullBacktestReport:
    resolved_costs = cost_model or load_full_backtest_cost_model()
    resolved_initial_balance = initial_balance_usd or env_float("FULL_BACKTEST_INITIAL_BALANCE_USD", 2000)

    paper_report: PaperTradingSessionReport = run_paper_trading_session(
        feature_snapshots=feature_snapshots,
        price_paths=price_paths,
        rules=rules,
        profile=profile,
        exposure_snapshot=exposure_snapshot,
        session_name=session_name,
        estimated_slippage_pct=resolved_costs.slippage_pct,
        initial_balance_usd=resolved_initial_balance,
    )

    adjusted_trades = apply_partial_fill_ratio_to_trades(
        paper_report.trades,
        partial_fill_ratio=resolved_costs.partial_fill_ratio,
    )

    metrics = calculate_full_backtest_metrics(
        trades=adjusted_trades,
        initial_balance_usd=resolved_initial_balance,
        routed_orders=int(paper_report.metrics.get("routed_orders", 0)),
        blocked_orders=int(paper_report.metrics.get("blocked_orders", 0)),
    )

    return FullBacktestReport(
        symbol=paper_report.symbol,
        completed_at=datetime.now(timezone.utc),
        cost_model=resolved_costs.model_dump(mode="json"),
        metrics=metrics.model_dump(mode="json"),
        trades=adjusted_trades,
    )


def export_full_backtest_report(
    report: FullBacktestReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "full_backtest",
) -> dict[str, Path]:
    resolved_output_dir = Path(output_dir or os.getenv("FULL_BACKTEST_OUTPUT_DIR", "artifacts/full_backtest"))
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")

    summary_path = resolved_output_dir / f"{safe_name}_summary.json"
    trades_path = resolved_output_dir / f"{safe_name}_trades.jsonl"

    summary_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with trades_path.open("w", encoding="utf-8") as file:
        for trade in report.trades:
            file.write(json.dumps(trade, ensure_ascii=False))
            file.write("\n")

    return {
        "summary": summary_path,
        "trades": trades_path,
    }


def full_backtest_report_to_dict(report: FullBacktestReport) -> dict[str, Any]:
    return report.model_dump(mode="json")