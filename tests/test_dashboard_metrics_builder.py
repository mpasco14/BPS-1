import json

from dashboard.config import DashboardConfig
from dashboard.metrics_builder import (
    build_calibration_dashboard,
    build_dashboard_summary,
    build_full_backtest_dashboard,
    build_paper_trading_dashboard,
    build_recent_trades,
)


def test_build_paper_trading_dashboard():
    report = {
        "metrics": {
            "net_pnl_usd": 2,
            "fill_rate": 1,
            "win_rate": 0.6,
            "profit_factor": 1.5,
        }
    }

    dashboard = build_paper_trading_dashboard(report, "paper.json")

    assert dashboard.available is True
    assert len(dashboard.cards) == 4


def test_build_full_backtest_dashboard():
    report = {
        "metrics": {
            "roi_pct": 0.01,
            "sharpe": 1.2,
            "max_drawdown_pct": 0.05,
            "profit_factor": 1.4,
        }
    }

    dashboard = build_full_backtest_dashboard(report, "backtest.json")

    assert dashboard.available is True
    assert len(dashboard.cards) == 4


def test_build_calibration_dashboard():
    report = {
        "samples": 10,
        "buckets_count": 10,
        "brier_score": 0.05,
        "expected_calibration_error": 0.04,
        "buckets": [],
    }

    dashboard = build_calibration_dashboard(report, "calibration.json")

    assert dashboard.available is True
    assert dashboard.metrics["brier_score"] == 0.05


def test_build_recent_trades():
    trades = [
        {
            "timestamp": "2026-05-15T18:00:00+00:00",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "routed": True,
            "blocked": False,
            "signal": {"direction": "LONG"},
            "pnl": {"net_pnl_usd": 2},
            "market_would_do": {"outcome": "take_profit"},
        }
    ]

    recent = build_recent_trades(trades, [], limit=10)

    assert len(recent) == 1
    assert recent[0]["side"] == "LONG"


def test_build_dashboard_summary(tmp_path):
    paper_dir = tmp_path / "paper"
    backtest_dir = tmp_path / "backtest"
    calibration_dir = tmp_path / "calibration"

    paper_dir.mkdir()
    backtest_dir.mkdir()
    calibration_dir.mkdir()

    (paper_dir / "session_summary.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "net_pnl_usd": 2,
                    "fill_rate": 1,
                    "win_rate": 0.6,
                    "profit_factor": 1.5,
                }
            }
        ),
        encoding="utf-8",
    )

    (paper_dir / "session_trades.jsonl").write_text(
        '{"symbol":"BTCUSDT","timeframe":"5m","routed":true,"blocked":false,"signal":{"direction":"LONG"},"pnl":{"net_pnl_usd":2},"market_would_do":{"outcome":"take_profit"}}\n',
        encoding="utf-8",
    )

    (backtest_dir / "full_summary.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "roi_pct": 0.01,
                    "sharpe": 1.2,
                    "max_drawdown_pct": 0.05,
                    "profit_factor": 1.4,
                }
            }
        ),
        encoding="utf-8",
    )

    (calibration_dir / "calibration.json").write_text(
        json.dumps(
            {
                "samples": 10,
                "buckets_count": 10,
                "brier_score": 0.05,
                "expected_calibration_error": 0.04,
                "buckets": [],
            }
        ),
        encoding="utf-8",
    )

    config = DashboardConfig(
        paper_trading_dir=paper_dir,
        full_backtest_dir=backtest_dir,
        model_evaluation_dir=calibration_dir,
    )

    summary = build_dashboard_summary(config)

    assert summary.paper_trading["available"] is True
    assert summary.full_backtest["available"] is True
    assert summary.calibration["available"] is True
    assert len(summary.recent_trades) == 1