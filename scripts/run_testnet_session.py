"""
Run a demo/testnet session report.

Nesta versão:
- --demo gera eventos simulados.
- Não envia ordens reais.
- Não envia ordens para testnet.
- Produz summary, events e quality report.

Exemplo:

    python scripts/run_testnet_session.py --demo --session-name testnet_demo --export
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from ops.testnet_quality_gate import evaluate_testnet_quality, export_testnet_quality_report
from ops.testnet_session import (
    TestnetOrderEvent,
    build_testnet_session_report,
    export_testnet_session_report,
    load_testnet_events_jsonl,
)


def build_demo_events(session_name: str) -> list[TestnetOrderEvent]:
    return [
        TestnetOrderEvent(
            session_name=session_name,
            symbol="BTCUSDT",
            timeframe="5m",
            side="BUY",
            quantity=0.01,
            requested_price=60000,
            executed_price=60001,
            status="FILLED",
            latency_ms=210,
            estimated_slippage_pct=0.0005,
            realized_slippage_pct=0.0004,
            fee_usd=0.05,
            pnl_usd=1.20,
        ),
        TestnetOrderEvent(
            session_name=session_name,
            symbol="BTCUSDT",
            timeframe="5m",
            side="SELL",
            quantity=0.01,
            requested_price=60100,
            executed_price=60099,
            status="FILLED",
            latency_ms=230,
            estimated_slippage_pct=0.0005,
            realized_slippage_pct=0.0004,
            fee_usd=0.05,
            pnl_usd=0.80,
        ),
        TestnetOrderEvent(
            session_name=session_name,
            symbol="BTCUSDT",
            timeframe="15m",
            side="BUY",
            quantity=0.01,
            requested_price=60200,
            status="CANCELED",
            latency_ms=150,
            estimated_slippage_pct=0.0005,
            realized_slippage_pct=0.0005,
            fee_usd=0.0,
            pnl_usd=0.0,
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run testnet session report.")

    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--events-jsonl", type=str, default=None)
    parser.add_argument("--session-name", type=str, default="testnet_session")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", type=str, default="artifacts/testnet")

    return parser.parse_args()


def load_events_from_args(args: argparse.Namespace) -> list[TestnetOrderEvent]:
    if args.demo:
        return build_demo_events(args.session_name)

    if args.events_jsonl:
        return load_testnet_events_jsonl(args.events_jsonl)

    return []


def build_session_payload(
    *,
    events: list[TestnetOrderEvent],
    session_name: str,
) -> dict[str, Any]:
    session_report = build_testnet_session_report(
        events=events,
        session_name=session_name,
    )

    quality_report = evaluate_testnet_quality(
        report=session_report,
    )

    return {
        "source": "testnet_session_runner",
        "passed": quality_report.passed,
        "status": quality_report.status,
        "session": session_report.model_dump(mode="json"),
        "quality": quality_report.model_dump(mode="json"),
    }


def main() -> int:
    args = parse_args()

    events = load_events_from_args(args)
    payload = build_session_payload(
        events=events,
        session_name=args.session_name,
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.export:
        session_report = build_testnet_session_report(
            events=events,
            session_name=args.session_name,
        )

        quality_report = evaluate_testnet_quality(
            report=session_report,
        )

        paths = export_testnet_session_report(
            session_report,
            output_dir=args.output_dir,
            name=args.session_name,
        )

        quality_path = export_testnet_quality_report(
            quality_report,
            output_dir=args.output_dir,
            name=f"{args.session_name}_quality",
        )

        print(f"Summary: {paths['summary']}")
        print(f"Events: {paths['events']}")
        print(f"Quality: {quality_path}")

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())