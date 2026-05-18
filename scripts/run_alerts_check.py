"""
Run one-shot alerts evaluation.

Uso:

    python scripts/run_alerts_check.py

Com simulação de falhas:

    python scripts/run_alerts_check.py --kill-switch-active
    python scripts/run_alerts_check.py --model-ood
    python scripts/run_alerts_check.py --api-error-count 5
    python scripts/run_alerts_check.py --ws-disconnected-seconds 45
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.alerts import (
    OperationalState,
    dispatch_console_alerts,
    evaluate_alerts,
    export_alert_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BTC Binance Futures alerts check."
    )

    parser.add_argument("--kill-switch-active", action="store_true")
    parser.add_argument("--daily-drawdown-pct", type=float, default=0.0)
    parser.add_argument("--websocket-connected", action="store_true", default=True)
    parser.add_argument("--ws-disconnected-seconds", type=float, default=0.0)
    parser.add_argument("--model-ood", action="store_true")
    parser.add_argument("--api-error-count", type=int, default=0)
    parser.add_argument("--open-positions", type=int, default=0)
    parser.add_argument("--btc-directional-exposure-pct", type=float, default=0.0)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", type=str, default="artifacts/alerts")
    parser.add_argument("--name", type=str, default="alerts_latest")

    return parser.parse_args()


def build_operational_state_from_args(args: argparse.Namespace) -> OperationalState:
    websocket_connected = args.websocket_connected

    if args.ws_disconnected_seconds > 0:
        websocket_connected = False

    return OperationalState(
        kill_switch_active=args.kill_switch_active,
        daily_drawdown_pct=args.daily_drawdown_pct,
        websocket_connected=websocket_connected,
        ws_disconnected_seconds=args.ws_disconnected_seconds,
        model_ood=args.model_ood,
        api_error_count=args.api_error_count,
        open_positions=args.open_positions,
        btc_directional_exposure_pct=args.btc_directional_exposure_pct,
    )


def main() -> int:
    args = parse_args()

    state = build_operational_state_from_args(args)
    result = evaluate_alerts(
        operational_state=state,
    )

    dispatch_console_alerts(result)

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_alert_evaluation(
            result,
            output_dir=args.output_dir,
            name=args.name,
        )

        print(f"Alert evaluation exported: {path}")

    return 1 if result.critical_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())