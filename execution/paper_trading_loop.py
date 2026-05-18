"""
Paper trading loop for Binance Futures.

Responsabilidades:
- Simular o fluxo completo sem capital real.
- Registrar ordens que seriam enviadas.
- Simular resultado do mercado usando TP/SL/time barrier.
- Calcular métricas: fill rate, slippage, edge realizado, PnL.
- Exportar resultados para JSONL/JSON.

Este módulo NÃO envia ordem real.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from accounting.pnl import TradePnl, summarize_pnl
from backtesting.execution_simulator import ExecutionSimulationResult, simulate_execution
from execution.binance_futures_client import BinanceFuturesConfig, BinanceFuturesRestClient
from execution.limit_order import SymbolTradingRules
from execution.order_router import InMemoryOrderRegistry, OrderRouteResult, route_signal_to_order
from risk.exposure import ExposureSnapshot
from risk.risk_manager import OrderRiskPlan, RiskProfile
from strategy.signal_engine import TradingSignal, generate_signal


load_dotenv()


class PaperTradingTradeRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "paper_trading_loop"

    timestamp: Any | None = None
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"

    routed: bool
    blocked: bool

    signal: dict[str, Any] | None = None
    route_result: dict[str, Any] | None = None

    order_would_send: dict[str, Any] | None = None
    market_would_do: dict[str, Any] | None = None

    pnl: dict[str, Any] | None = None

    estimated_slippage_pct: float = 0.0
    realized_entry_slippage_pct: float | None = None
    realized_exit_slippage_pct: float | None = None
    slippage_error_pct: float | None = None

    expected_edge: float | None = None
    realized_edge: float | None = None

    blockers: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class PaperTradingMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_features: int
    routed_orders: int
    blocked_orders: int

    simulated_trades: int
    filled_trades: int

    fill_rate: float

    net_pnl_usd: float
    gross_pnl_usd: float

    win_rate: float
    profit_factor: float | None

    average_realized_edge: float | None
    average_slippage_error_pct: float | None

    pnl_summary: dict[str, Any]


class PaperTradingSessionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "paper_trading_loop"
    session_name: str

    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    metrics: dict[str, Any]
    trades: list[dict[str, Any]] = Field(default_factory=list)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    if isinstance(value, int | float):
        numeric = int(value)

        if numeric >= 1_000_000_000_000:
            numeric = numeric // 1000

        return datetime.fromtimestamp(numeric, tz=timezone.utc)

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return None

        if stripped.isdigit():
            return parse_timestamp(int(stripped))

        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    return None


def now_for_feature(feature: dict[str, Any]) -> datetime | None:
    timestamp = parse_timestamp(feature.get("timestamp"))

    if timestamp is None:
        return None

    return timestamp + timedelta(seconds=60)


def sort_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        features,
        key=lambda item: parse_timestamp(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
    )


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_entry_price(feature: dict[str, Any]) -> float:
    field_name = os.getenv("PAPER_TRADING_ENTRY_PRICE_FIELD", "mark_price")

    candidates = [
        feature.get(field_name),
        feature.get("mark_price"),
        feature.get("index_price"),
        feature.get("close"),
    ]

    btc_features = feature.get("btc_features") or {}
    technical = btc_features.get("technical") or {}

    candidates.extend(
        [
            technical.get("latest_close"),
            technical.get("mark_price"),
            technical.get("index_price"),
        ]
    )

    for candidate in candidates:
        parsed = safe_float(candidate)

        if parsed is not None and parsed > 0:
            return parsed

    raise ValueError("não foi possível extrair entry_price válido")


def price_path_key(feature: dict[str, Any]) -> str:
    symbol = str(feature.get("symbol") or os.getenv("PAPER_TRADING_SYMBOL", "BTCUSDT")).upper()
    timeframe = str(feature.get("timeframe") or os.getenv("PAPER_TRADING_DEFAULT_TIMEFRAME", "5m"))
    timestamp = str(feature.get("timestamp") or "")

    return f"{symbol}:{timeframe}:{timestamp}"


def get_price_path(
    feature: dict[str, Any],
    price_paths: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    key = price_path_key(feature)

    if key in price_paths:
        return price_paths[key]

    timestamp = str(feature.get("timestamp") or "")

    if timestamp in price_paths:
        return price_paths[timestamp]

    return price_paths.get("default", [])


def extract_expected_value(feature: dict[str, Any]) -> float | None:
    direct = safe_float(feature.get("expected_value_usd"))

    if direct is not None:
        return direct

    prediction = feature.get("prediction")

    if isinstance(prediction, dict):
        return safe_float(prediction.get("expected_value_usd"))

    return None


def signal_from_feature(feature: dict[str, Any]) -> TradingSignal:
    signal = generate_signal(feature, now=now_for_feature(feature))

    expected_value = extract_expected_value(feature)

    if expected_value is None:
        return signal

    stop_loss = env_float("RISK_GROSS_STOP_LOSS_USD", 1.05)

    if stop_loss <= 0:
        return signal

    edge = expected_value / stop_loss

    return signal.model_copy(
        update={
            "edge": edge,
            "prediction": {"expected_value_usd": expected_value},
        }
    )


def extract_order_plan(route_result: OrderRouteResult) -> OrderRiskPlan | None:
    record = route_result.record
    assessment = record.get("risk_assessment") or {}
    order_plan = assessment.get("order_plan")

    if not order_plan:
        return None

    return OrderRiskPlan.model_validate(order_plan)


def calculate_entry_slippage_pct(simulation: ExecutionSimulationResult) -> float | None:
    requested = simulation.entry_price_requested
    filled = simulation.entry_price_filled

    if requested <= 0:
        return None

    return abs(filled - requested) / requested


def calculate_exit_slippage_pct(simulation: ExecutionSimulationResult) -> float | None:
    raw = simulation.exit_price_raw
    filled = simulation.exit_price_filled

    if raw <= 0:
        return None

    return abs(filled - raw) / raw


def calculate_realized_edge(
    *,
    pnl: TradePnl,
    order_plan: OrderRiskPlan,
) -> float | None:
    denominator = order_plan.gross_stop_loss_usd

    if denominator <= 0:
        return None

    return pnl.net_pnl_usd / denominator


def build_paper_client() -> BinanceFuturesRestClient:
    config = BinanceFuturesConfig(execution_mode="paper")

    return BinanceFuturesRestClient(config=config)


def run_paper_trading_session(
    *,
    feature_snapshots: list[dict[str, Any]],
    price_paths: dict[str, list[dict[str, Any]]],
    rules: SymbolTradingRules,
    profile: RiskProfile | None = None,
    exposure_snapshot: ExposureSnapshot | None = None,
    session_name: str | None = None,
    estimated_slippage_pct: float | None = None,
    initial_balance_usd: float | None = None,
) -> PaperTradingSessionReport:
    resolved_session_name = session_name or os.getenv("PAPER_TRADING_SESSION_NAME", "dev_session")
    slippage = estimated_slippage_pct if estimated_slippage_pct is not None else env_float("PAPER_TRADING_ESTIMATED_SLIPPAGE_PCT", 0.0005)
    initial_balance = initial_balance_usd if initial_balance_usd is not None else env_float("PAPER_TRADING_INITIAL_BANKROLL_USD", 2000)

    registry = InMemoryOrderRegistry()
    client = build_paper_client()

    trade_records: list[PaperTradingTradeRecord] = []
    pnl_trades: list[TradePnl] = []

    routed_orders = 0
    blocked_orders = 0
    simulated_trades = 0
    filled_trades = 0

    realized_edges: list[float] = []
    slippage_errors: list[float] = []

    for feature in sort_features(feature_snapshots):
        signal = signal_from_feature(feature)

        try:
            entry_price = extract_entry_price(feature)
        except ValueError as exc:
            blocked_orders += 1
            trade_records.append(
                PaperTradingTradeRecord(
                    timestamp=feature.get("timestamp"),
                    symbol=str(feature.get("symbol") or "BTCUSDT"),
                    timeframe=str(feature.get("timeframe") or "5m"),
                    routed=False,
                    blocked=True,
                    signal=signal.model_dump(mode="json"),
                    blockers=[str(exc)],
                )
            )
            continue

        route = route_signal_to_order(
            signal=signal,
            entry_price=entry_price,
            rules=rules,
            client=client,
            profile=profile,
            exposure_snapshot=exposure_snapshot,
            market_liquidity_usd=safe_float(feature.get("binance_liquidity_usd")),
            registry=registry,
        )

        record = route.record

        if route.decision != "ROUTED":
            blocked_orders += 1
            trade_records.append(
                PaperTradingTradeRecord(
                    timestamp=feature.get("timestamp"),
                    symbol=str(feature.get("symbol") or "BTCUSDT"),
                    timeframe=str(feature.get("timeframe") or "5m"),
                    routed=False,
                    blocked=True,
                    signal=signal.model_dump(mode="json"),
                    route_result=record,
                    blockers=list(record.get("blockers") or []),
                    reasons=list(record.get("reasons") or []),
                    estimated_slippage_pct=slippage,
                    expected_edge=safe_float(getattr(signal, "edge", None)),
                )
            )
            continue

        routed_orders += 1

        order_plan = extract_order_plan(route)

        if order_plan is None:
            blocked_orders += 1
            trade_records.append(
                PaperTradingTradeRecord(
                    timestamp=feature.get("timestamp"),
                    symbol=str(feature.get("symbol") or "BTCUSDT"),
                    timeframe=str(feature.get("timeframe") or "5m"),
                    routed=False,
                    blocked=True,
                    signal=signal.model_dump(mode="json"),
                    route_result=record,
                    blockers=["missing_order_plan"],
                    estimated_slippage_pct=slippage,
                    expected_edge=safe_float(getattr(signal, "edge", None)),
                )
            )
            continue

        path = get_price_path(feature, price_paths)

        simulation = simulate_execution(
            order_plan=order_plan,
            price_path=path,
            slippage_pct=slippage,
            entry_fee_usd=env_float("PAPER_TRADING_ENTRY_FEE_USD", 0.05),
            exit_fee_usd=env_float("PAPER_TRADING_EXIT_FEE_USD", 0.05),
            funding_cost_usd=env_float("PAPER_TRADING_FUNDING_COST_USD", 0.0),
        )

        simulated_trades += 1

        if simulation.outcome != "no_data":
            filled_trades += 1

        pnl = TradePnl.model_validate(simulation.pnl)
        pnl_trades.append(pnl)

        entry_slippage = calculate_entry_slippage_pct(simulation)
        exit_slippage = calculate_exit_slippage_pct(simulation)

        max_realized_slippage = max(
            value for value in [entry_slippage, exit_slippage] if value is not None
        )

        slippage_error = max_realized_slippage - slippage

        slippage_errors.append(slippage_error)

        realized_edge = calculate_realized_edge(
            pnl=pnl,
            order_plan=order_plan,
        )

        if realized_edge is not None:
            realized_edges.append(realized_edge)

        trade_records.append(
            PaperTradingTradeRecord(
                timestamp=feature.get("timestamp"),
                symbol=simulation.symbol,
                timeframe=simulation.timeframe,
                routed=True,
                blocked=False,
                signal=signal.model_dump(mode="json"),
                route_result=record,
                order_would_send=record.get("order_payload"),
                market_would_do=simulation.model_dump(mode="json"),
                pnl=pnl.model_dump(mode="json"),
                estimated_slippage_pct=slippage,
                realized_entry_slippage_pct=entry_slippage,
                realized_exit_slippage_pct=exit_slippage,
                slippage_error_pct=slippage_error,
                expected_edge=safe_float(getattr(signal, "edge", None)),
                realized_edge=realized_edge,
                blockers=[],
                reasons=list(record.get("reasons") or []),
            )
        )

    pnl_summary = summarize_pnl(
        pnl_trades,
        initial_balance_usd=initial_balance,
    )

    metrics = PaperTradingMetrics(
        total_features=len(feature_snapshots),
        routed_orders=routed_orders,
        blocked_orders=blocked_orders,
        simulated_trades=simulated_trades,
        filled_trades=filled_trades,
        fill_rate=filled_trades / routed_orders if routed_orders > 0 else 0.0,
        net_pnl_usd=pnl_summary.net_pnl_usd,
        gross_pnl_usd=pnl_summary.gross_pnl_usd,
        win_rate=pnl_summary.win_rate,
        profit_factor=pnl_summary.profit_factor,
        average_realized_edge=sum(realized_edges) / len(realized_edges) if realized_edges else None,
        average_slippage_error_pct=sum(slippage_errors) / len(slippage_errors) if slippage_errors else None,
        pnl_summary=pnl_summary.model_dump(mode="json"),
    )

    return PaperTradingSessionReport(
        session_name=resolved_session_name,
        symbol=os.getenv("PAPER_TRADING_SYMBOL", "BTCUSDT"),
        completed_at=datetime.now(timezone.utc),
        metrics=metrics.model_dump(mode="json"),
        trades=[trade.model_dump(mode="json") for trade in trade_records],
    )


def export_paper_trading_report(
    report: PaperTradingSessionReport,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    resolved_output_dir = Path(output_dir or os.getenv("PAPER_TRADING_OUTPUT_DIR", "artifacts/paper_trading"))
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    session = report.session_name.replace("/", "_").replace("\\", "_")

    summary_path = resolved_output_dir / f"{session}_summary.json"
    trades_path = resolved_output_dir / f"{session}_trades.jsonl"

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


def load_paper_trading_trades(path: str | Path) -> list[PaperTradingTradeRecord]:
    rows: list[PaperTradingTradeRecord] = []

    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            rows.append(PaperTradingTradeRecord.model_validate(json.loads(line)))

    return rows


def paper_report_to_dict(report: PaperTradingSessionReport) -> dict[str, Any]:
    return report.model_dump(mode="json")