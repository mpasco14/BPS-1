"""
Dashboard metrics builder.

Responsabilidades:
- Transformar relatórios brutos em métricas de dashboard.
- Criar cards padronizados.
- Consolidar paper trading, full backtest e calibração.
"""

from __future__ import annotations

from typing import Any

from dashboard.config import DashboardConfig
from dashboard.data_loader import (
    load_latest_calibration_report,
    load_latest_full_backtest_report,
    load_latest_full_backtest_trades,
    load_latest_paper_trading_report,
    load_latest_paper_trading_trades,
    normalize_path,
)
from dashboard.schemas import (
    CalibrationDashboard,
    DashboardSummary,
    FullBacktestDashboard,
    MetricCard,
    PaperTradingDashboard,
    RecentTrade,
)


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def card_status(
    value: float | int | None,
    *,
    good_above: float | None = None,
    bad_below: float | None = None,
    good_below: float | None = None,
    bad_above: float | None = None,
) -> str:
    if value is None:
        return "neutral"

    numeric = float(value)

    if good_above is not None and numeric >= good_above:
        return "good"

    if bad_below is not None and numeric <= bad_below:
        return "bad"

    if good_below is not None and numeric <= good_below:
        return "good"

    if bad_above is not None and numeric >= bad_above:
        return "bad"

    return "neutral"


def make_card(
    *,
    key: str,
    label: str,
    value: float | int | str | None,
    unit: str | None = None,
    status: str = "neutral",
    description: str | None = None,
) -> dict[str, Any]:
    return MetricCard(
        key=key,
        label=label,
        value=value,
        unit=unit,
        status=status,
        description=description,
    ).model_dump(mode="json")


def build_paper_trading_dashboard(
    report: dict[str, Any] | None,
    source_file: str | None,
) -> PaperTradingDashboard:
    if not report:
        return PaperTradingDashboard(
            available=False,
            source_file=source_file,
            metrics={},
            cards=[],
        )

    metrics = report.get("metrics") or {}

    net_pnl = safe_float(metrics.get("net_pnl_usd"))
    fill_rate = safe_float(metrics.get("fill_rate"))
    win_rate = safe_float(metrics.get("win_rate"))
    profit_factor = safe_float(metrics.get("profit_factor"))

    cards = [
        make_card(
            key="paper_net_pnl_usd",
            label="Paper Net PnL",
            value=net_pnl,
            unit="USD",
            status=card_status(net_pnl, good_above=0, bad_below=0),
        ),
        make_card(
            key="paper_fill_rate",
            label="Fill Rate",
            value=fill_rate,
            unit="ratio",
            status=card_status(fill_rate, good_above=0.70, bad_below=0.30),
        ),
        make_card(
            key="paper_win_rate",
            label="Win Rate",
            value=win_rate,
            unit="ratio",
            status=card_status(win_rate, good_above=0.50, bad_below=0.40),
        ),
        make_card(
            key="paper_profit_factor",
            label="Profit Factor",
            value=profit_factor,
            unit=None,
            status=card_status(profit_factor, good_above=1.2, bad_below=1.0),
        ),
    ]

    return PaperTradingDashboard(
        available=True,
        source_file=source_file,
        metrics=metrics,
        cards=cards,
    )


def build_full_backtest_dashboard(
    report: dict[str, Any] | None,
    source_file: str | None,
) -> FullBacktestDashboard:
    if not report:
        return FullBacktestDashboard(
            available=False,
            source_file=source_file,
            metrics={},
            cards=[],
        )

    metrics = report.get("metrics") or {}

    roi = safe_float(metrics.get("roi_pct"))
    sharpe = safe_float(metrics.get("sharpe"))
    max_drawdown = safe_float(metrics.get("max_drawdown_pct"))
    profit_factor = safe_float(metrics.get("profit_factor"))

    cards = [
        make_card(
            key="backtest_roi_pct",
            label="Backtest ROI",
            value=roi,
            unit="ratio",
            status=card_status(roi, good_above=0, bad_below=0),
        ),
        make_card(
            key="backtest_sharpe",
            label="Sharpe",
            value=sharpe,
            status=card_status(sharpe, good_above=1.0, bad_below=0.0),
        ),
        make_card(
            key="backtest_max_drawdown_pct",
            label="Max Drawdown",
            value=max_drawdown,
            unit="ratio",
            status=card_status(max_drawdown, good_below=0.10, bad_above=0.20),
        ),
        make_card(
            key="backtest_profit_factor",
            label="Profit Factor",
            value=profit_factor,
            status=card_status(profit_factor, good_above=1.2, bad_below=1.0),
        ),
    ]

    return FullBacktestDashboard(
        available=True,
        source_file=source_file,
        metrics=metrics,
        cards=cards,
    )


def build_calibration_dashboard(
    report: dict[str, Any] | None,
    source_file: str | None,
) -> CalibrationDashboard:
    if not report:
        return CalibrationDashboard(
            available=False,
            source_file=source_file,
            metrics={},
            buckets=[],
            cards=[],
        )

    brier = safe_float(report.get("brier_score"))
    ece = safe_float(report.get("expected_calibration_error"))

    cards = [
        make_card(
            key="brier_score",
            label="Brier Score",
            value=brier,
            status=card_status(brier, good_below=0.20, bad_above=0.25),
        ),
        make_card(
            key="expected_calibration_error",
            label="ECE",
            value=ece,
            status=card_status(ece, good_below=0.05, bad_above=0.15),
        ),
    ]

    return CalibrationDashboard(
        available=True,
        source_file=source_file,
        metrics={
            "samples": report.get("samples"),
            "buckets_count": report.get("buckets_count"),
            "brier_score": brier,
            "expected_calibration_error": ece,
        },
        buckets=list(report.get("buckets") or []),
        cards=cards,
    )


def trade_to_recent_trade(row: dict[str, Any]) -> RecentTrade:
    signal = row.get("signal") or {}
    pnl = row.get("pnl") or {}
    market = row.get("market_would_do") or {}

    side = signal.get("direction")
    outcome = market.get("outcome")

    return RecentTrade(
        timestamp=row.get("timestamp"),
        symbol=row.get("symbol"),
        timeframe=row.get("timeframe"),
        routed=row.get("routed"),
        blocked=row.get("blocked"),
        side=side,
        net_pnl_usd=safe_float(pnl.get("net_pnl_usd")),
        outcome=outcome,
        blockers=list(row.get("blockers") or []),
    )


def build_recent_trades(
    paper_trades: list[dict[str, Any]],
    full_backtest_trades: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    combined = list(paper_trades) + list(full_backtest_trades)
    combined = combined[-limit:]

    return [
        trade_to_recent_trade(row).model_dump(mode="json")
        for row in combined
    ]


def build_dashboard_summary(config: DashboardConfig) -> DashboardSummary:
    paper_report, paper_path = load_latest_paper_trading_report(config.paper_trading_dir)
    paper_trades, _ = load_latest_paper_trading_trades(config.paper_trading_dir)

    full_report, full_path = load_latest_full_backtest_report(config.full_backtest_dir)
    full_trades, _ = load_latest_full_backtest_trades(config.full_backtest_dir)

    calibration_report, calibration_path = load_latest_calibration_report(config.model_evaluation_dir)

    paper_dashboard = build_paper_trading_dashboard(
        paper_report if config.show_paper_trading else None,
        normalize_path(paper_path),
    )

    full_dashboard = build_full_backtest_dashboard(
        full_report if config.show_full_backtest else None,
        normalize_path(full_path),
    )

    calibration_dashboard = build_calibration_dashboard(
        calibration_report if config.show_calibration else None,
        normalize_path(calibration_path),
    )

    recent_trades = build_recent_trades(
        paper_trades=paper_trades,
        full_backtest_trades=full_trades,
        limit=config.max_recent_trades,
    )

    return DashboardSummary(
        theme=config.theme,
        refresh_seconds=config.refresh_seconds,
        paper_trading=paper_dashboard.model_dump(mode="json"),
        full_backtest=full_dashboard.model_dump(mode="json"),
        calibration=calibration_dashboard.model_dump(mode="json"),
        recent_trades=recent_trades,
    )


def dashboard_summary_to_dict(summary: DashboardSummary) -> dict[str, Any]:
    return summary.model_dump(mode="json")