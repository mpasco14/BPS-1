"""
Backtest engine for Binance Futures.

Responsabilidades:
- Rodar ciclo completo de backtest:
  features -> signal -> risk -> execution simulation -> PnL.
- Aplicar custos, slippage, funding e regra TP/SL/time barrier.
- Gerar relatório com métricas agregadas.
- Preparar base para dataset histórico e modelos.

Este módulo NÃO executa ordens reais.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from accounting.pnl import TradePnl, summarize_pnl
from backtesting.execution_simulator import simulate_execution
from risk.risk_manager import AccountRiskState, RiskProfile, assess_signal_risk
from strategy.signal_engine import generate_signal


load_dotenv()


class BacktestTradeResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "backtest"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str

    timestamp: Any | None = None

    signal: dict[str, Any]
    risk_assessment: dict[str, Any]

    executed: bool
    simulation: dict[str, Any] | None = None
    pnl: dict[str, Any] | None = None

    blockers: list[str] = Field(default_factory=list)


class BacktestReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "backtest"
    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"

    total_features: int
    signals_enter: int
    risk_approved: int
    executed_trades: int
    blocked_trades: int

    pnl_summary: dict[str, Any]

    trades: list[dict[str, Any]] = Field(default_factory=list)


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def env_float(name: str, default: float) -> float:
    parsed = safe_float(os.getenv(name))

    if parsed is None:
        return default

    return parsed


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


def sort_features_by_timestamp(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        features,
        key=lambda item: parse_timestamp(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
    )


def backtest_now_for_feature(feature: dict[str, Any]) -> datetime | None:
    """
    Em backtest, não queremos bloquear features históricas por staleness
    usando o relógio atual. Então usamos timestamp + 60s como 'now'
    para o signal_engine.
    """
    timestamp = parse_timestamp(feature.get("timestamp"))

    if timestamp is None:
        return None

    return timestamp + timedelta(seconds=60)


def price_path_key(feature: dict[str, Any]) -> str:
    symbol = str(feature.get("symbol") or "BTCUSDT").upper()
    timeframe = str(feature.get("timeframe") or "5m")
    timestamp = str(feature.get("timestamp") or "")

    return f"{symbol}:{timeframe}:{timestamp}"


def get_price_path(
    *,
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


def extract_entry_price(feature: dict[str, Any], *, field_name: str | None = None) -> float:
    selected_field = field_name or os.getenv("BACKTEST_ENTRY_PRICE_FIELD", "mark_price")

    candidates = [
        feature.get(selected_field),
        feature.get("mark_price"),
        feature.get("index_price"),
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

    raise ValueError("não foi possível extrair entry_price válido do feature snapshot")


def update_account_state(
    *,
    previous: AccountRiskState,
    pnl_usd: float,
) -> AccountRiskState:
    consecutive_losses = previous.consecutive_losses + 1 if pnl_usd < 0 else 0

    return AccountRiskState(
        daily_pnl_usd=previous.daily_pnl_usd + pnl_usd,
        consecutive_losses=consecutive_losses,
        open_positions=0,
        open_orders=0,
        kill_switch_active=previous.kill_switch_active,
    )


def run_backtest(
    *,
    feature_snapshots: list[dict[str, Any]],
    price_paths: dict[str, list[dict[str, Any]]],
    profile: RiskProfile | None = None,
    initial_balance_usd: float | None = None,
) -> BacktestReport:
    initial_balance = initial_balance_usd or env_float("BACKTEST_INITIAL_BANKROLL", 10000.0)

    sorted_features = sort_features_by_timestamp(feature_snapshots)

    account_state = AccountRiskState()
    trade_results: list[BacktestTradeResult] = []
    pnl_trades: list[TradePnl] = []

    signals_enter = 0
    risk_approved = 0
    executed_trades = 0
    blocked_trades = 0

    for feature in sorted_features:
        now = backtest_now_for_feature(feature)

        signal = generate_signal(feature, now=now)

        if signal.decision == "ENTER":
            signals_enter += 1

        try:
            entry_price = extract_entry_price(feature)
        except ValueError as exc:
            blocked_trades += 1
            trade_results.append(
                BacktestTradeResult(
                    venue=str(feature.get("venue") or "binance_futures"),
                    symbol=str(feature.get("symbol") or "BTCUSDT"),
                    timeframe=str(feature.get("timeframe") or "5m"),
                    timestamp=feature.get("timestamp"),
                    signal=signal.model_dump(mode="json"),
                    risk_assessment={},
                    executed=False,
                    blockers=[str(exc)],
                )
            )
            continue

        assessment = assess_signal_risk(
            signal=signal,
            entry_price=entry_price,
            account_state=account_state,
            profile=profile,
        )

        if assessment.decision == "APPROVED":
            risk_approved += 1
        else:
            blocked_trades += 1
            trade_results.append(
                BacktestTradeResult(
                    venue=assessment.venue,
                    symbol=assessment.symbol,
                    timeframe=assessment.timeframe,
                    timestamp=feature.get("timestamp"),
                    signal=signal.model_dump(mode="json"),
                    risk_assessment=assessment.model_dump(mode="json"),
                    executed=False,
                    blockers=assessment.blockers,
                )
            )
            continue

        assert assessment.order_plan is not None

        path = get_price_path(feature=feature, price_paths=price_paths)

        simulation = simulate_execution(
            order_plan=assessment.order_plan,
            price_path=path,
            slippage_pct=env_float("BACKTEST_SLIPPAGE_PCT", 0.0005),
            entry_fee_usd=env_float("BACKTEST_ENTRY_FEE_USD", 0.05),
            exit_fee_usd=env_float("BACKTEST_EXIT_FEE_USD", 0.05),
            funding_cost_usd=env_float("BACKTEST_FUNDING_COST_USD", 0.0),
        )

        pnl = TradePnl.model_validate(simulation.pnl)
        pnl_trades.append(pnl)

        account_state = update_account_state(
            previous=account_state,
            pnl_usd=pnl.net_pnl_usd,
        )

        executed_trades += 1

        trade_results.append(
            BacktestTradeResult(
                venue=assessment.venue,
                symbol=assessment.symbol,
                timeframe=assessment.timeframe,
                timestamp=feature.get("timestamp"),
                signal=signal.model_dump(mode="json"),
                risk_assessment=assessment.model_dump(mode="json"),
                executed=True,
                simulation=simulation.model_dump(mode="json"),
                pnl=pnl.model_dump(mode="json"),
                blockers=[],
            )
        )

    pnl_summary = summarize_pnl(
        pnl_trades,
        initial_balance_usd=initial_balance,
    )

    return BacktestReport(
        venue=os.getenv("BACKTEST_PRIMARY_VENUE", "binance_futures"),
        symbol=os.getenv("BACKTEST_SYMBOL", "BTCUSDT"),
        total_features=len(feature_snapshots),
        signals_enter=signals_enter,
        risk_approved=risk_approved,
        executed_trades=executed_trades,
        blocked_trades=blocked_trades,
        pnl_summary=pnl_summary.model_dump(mode="json"),
        trades=[trade.model_dump(mode="json") for trade in trade_results],
    )


def backtest_report_to_dict(report: BacktestReport) -> dict[str, Any]:
    return report.model_dump(mode="json")