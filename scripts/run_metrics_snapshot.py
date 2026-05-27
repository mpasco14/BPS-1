from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from observability.metrics_registry import build_core_metrics_snapshot, export_metrics_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build metrics snapshot demo.")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--path", default="artifacts/observability/metrics_snapshot_demo.json")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    snapshot = build_core_metrics_snapshot(
        live_performance={
            "passed": True,
            "fill_rate": 0.75,
            "rejection_rate": 0.02,
            "net_pnl_usd": 3.5,
            "max_drawdown_usd": 1.2,
            "average_slippage_pct": 0.0005,
            "average_latency_ms": 220,
        },
        live_risk_audit={
            "passed": True,
            "critical_findings_count": 0,
            "blocking_findings_count": 0,
            "realized_daily_pnl_usd": 3.5,
        },
        drift_report={
            "passed": True,
            "ood_rate": 0.05,
            "brier_score": 0.12,
            "expected_calibration_error": 0.08,
        },
        production_guard={
            "passed": True,
            "blocking_fail_count": 0,
        },
        strategy_health={
            "passed": True,
            "health_score": 0.82,
        },
        sentiment={
            "btc_sentiment_index": 65,
            "fear_greed_value": 65,
            "panic_score": 10,
            "euphoria_score": 35,
            "sentiment_confidence": 0.7,
            "items_count": 5,
        },
    )

    print(json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_metrics_snapshot(snapshot, path=args.path)
        print(f"Metrics snapshot exported: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())