from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from execution.live_micro_session import (
    LiveMicroTradeRequest,
    export_live_micro_session_result,
    run_live_micro_session,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live micro-capital session.")

    parser.add_argument("--session-name", default="live_micro_session")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--quantity", type=float, default=0.01)
    parser.add_argument("--price", type=float, default=60000)
    parser.add_argument("--notional-usd", type=float, default=600)
    parser.add_argument("--margin-usd", type=float, default=20)
    parser.add_argument("--leverage", type=int, default=30)

    parser.add_argument("--safety-gate-approved", action="store_true")
    parser.add_argument("--capital-ramp-approved", action="store_true")
    parser.add_argument("--live-preflight-passed", action="store_true")

    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/live")
    parser.add_argument("--name", default="live_micro_session_latest")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    request = LiveMicroTradeRequest(
        session_name=args.session_name,
        symbol=args.symbol,
        side=args.side,
        quantity=args.quantity,
        price=args.price,
        notional_usd=args.notional_usd,
        margin_usd=args.margin_usd,
        leverage=args.leverage,
        safety_gate_approved=args.safety_gate_approved,
        capital_ramp_approved=args.capital_ramp_approved,
        live_preflight_passed=args.live_preflight_passed,
    )

    result = run_live_micro_session(request=request)

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.export:
        path = export_live_micro_session_result(
            result,
            output_dir=args.output_dir,
            name=args.name,
        )
        print(f"Live micro session exported: {path}")

    return 0 if result.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())