"""
Paper trading session runner.

Uso básico:

    python scripts/run_paper_trading_session.py --demo --session-name demo_session

Uso com arquivos:

    python scripts/run_paper_trading_session.py ^
        --features artifacts/datasets/features.jsonl ^
        --price-paths artifacts/datasets/price_paths.json ^
        --session-name paper_001

Este script NÃO envia ordens reais.
Ele usa execution.paper_trading_loop em modo paper.
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

from execution.limit_order import SymbolTradingRules, rules_from_symbol_info
from execution.paper_trading_loop import (
    export_paper_trading_report,
    price_path_key,
    run_paper_trading_session,
)
from risk.exposure import ExposureSnapshot
from risk.risk_manager import RiskProfile, get_default_risk_profile


def load_json_or_jsonl(path: str | Path) -> Any:
    input_path = Path(path)

    if not input_path.exists():
        raise FileNotFoundError(f"arquivo não encontrado: {input_path}")

    if input_path.suffix.lower() == ".jsonl":
        rows = []

        with input_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                rows.append(json.loads(line))

        return rows

    return json.loads(input_path.read_text(encoding="utf-8"))


def load_feature_snapshots(path: str | Path) -> list[dict[str, Any]]:
    payload = load_json_or_jsonl(path)

    if isinstance(payload, list):
        return [dict(item) for item in payload]

    if isinstance(payload, dict) and isinstance(payload.get("features"), list):
        return [dict(item) for item in payload["features"]]

    raise ValueError("features precisa ser lista JSON/JSONL ou dict com chave 'features'.")


def load_price_paths(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    payload = load_json_or_jsonl(path)

    if not isinstance(payload, dict):
        raise ValueError("price_paths precisa ser um JSON dict.")

    normalized: dict[str, list[dict[str, Any]]] = {}

    for key, value in payload.items():
        if not isinstance(value, list):
            raise ValueError(f"price path inválido para chave: {key}")

        normalized[str(key)] = [dict(item) for item in value]

    return normalized


def sample_symbol_info() -> dict[str, Any]:
    return {
        "symbol": "BTCUSDT",
        "filters": [
            {
                "filterType": "PRICE_FILTER",
                "tickSize": "0.10",
            },
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.001",
                "stepSize": "0.001",
            },
            {
                "filterType": "MIN_NOTIONAL",
                "notional": "5",
            },
        ],
    }


def load_rules(path: str | Path | None = None) -> SymbolTradingRules:
    if path is None:
        return rules_from_symbol_info(sample_symbol_info())

    payload = load_json_or_jsonl(path)

    if not isinstance(payload, dict):
        raise ValueError("symbol rules precisa ser um JSON dict.")

    # Aceita tanto o symbol_info completo quanto um exchangeInfo reduzido.
    if "symbols" in payload:
        symbols = payload.get("symbols") or []

        for symbol_info in symbols:
            if str(symbol_info.get("symbol", "")).upper() == "BTCUSDT":
                return rules_from_symbol_info(symbol_info)

        raise ValueError("BTCUSDT não encontrado em exchangeInfo.")

    return rules_from_symbol_info(payload)


def build_default_exposure(initial_bankroll_usd: float) -> ExposureSnapshot:
    return ExposureSnapshot(
        total_bankroll_usd=initial_bankroll_usd,
        daily_pnl_usd=0.0,
        open_positions=0,
        exposure_per_market={},
        exposure_by_timeframe={},
        btc_directional_exposure_usd=0.0,
    )


def build_demo_features() -> list[dict[str, Any]]:
    return [
        {
            "timestamp": "2026-05-15T18:00:00+00:00",
            "venue": "binance_futures",
            "instrument_id": "BTCUSDT",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "tech_score": 0.9,
            "microstructure_score": 0.4,
            "onchain_score": 0.05,
            "sentiment_score": 0.03,
            "combined_score": 0.9,
            "binance_spread_pct": 0.0001,
            "binance_liquidity_usd": 100000,
            "mark_price": 60000,
            "expected_value_usd": 0.50,
            "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
        },
        {
            "timestamp": "2026-05-15T18:05:00+00:00",
            "venue": "binance_futures",
            "instrument_id": "BTCUSDT",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "tech_score": -0.9,
            "microstructure_score": -0.4,
            "onchain_score": -0.05,
            "sentiment_score": -0.03,
            "combined_score": -0.9,
            "binance_spread_pct": 0.0001,
            "binance_liquidity_usd": 100000,
            "mark_price": 60000,
            "expected_value_usd": 0.50,
            "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
        },
        {
            "timestamp": "2026-05-15T18:10:00+00:00",
            "venue": "binance_futures",
            "instrument_id": "BTCUSDT",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "tech_score": 0.1,
            "microstructure_score": 0.0,
            "onchain_score": 0.0,
            "sentiment_score": 0.0,
            "combined_score": 0.1,
            "binance_spread_pct": 0.0001,
            "binance_liquidity_usd": 100000,
            "mark_price": 60000,
            "expected_value_usd": 0.01,
            "btc_features": {"orderbook": {"is_tradeable": True, "blockers": []}},
        },
    ]


def build_demo_price_paths(features: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    price_paths: dict[str, list[dict[str, Any]]] = {}

    for feature in features:
        key = price_path_key(feature)
        combined_score = float(feature.get("combined_score", 0.0))

        if combined_score > 0:
            price_paths[key] = [
                {
                    "timestamp": "2026-05-15T18:05:00+00:00",
                    "high": 60500,
                    "low": 60000,
                    "close": 60500,
                }
            ]
        elif combined_score < 0:
            price_paths[key] = [
                {
                    "timestamp": "2026-05-15T18:10:00+00:00",
                    "high": 60000,
                    "low": 59500,
                    "close": 59500,
                }
            ]
        else:
            price_paths[key] = [
                {
                    "timestamp": "2026-05-15T18:15:00+00:00",
                    "high": 60050,
                    "low": 59950,
                    "close": 60000,
                }
            ]

    return price_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Binance Futures paper trading session without real capital."
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Usa features e price paths simulados.",
    )
    parser.add_argument(
        "--features",
        type=str,
        default=None,
        help="Arquivo JSON/JSONL com feature snapshots.",
    )
    parser.add_argument(
        "--price-paths",
        type=str,
        default=None,
        help="Arquivo JSON com price paths por chave.",
    )
    parser.add_argument(
        "--rules",
        type=str,
        default=None,
        help="Arquivo JSON com symbol_info ou exchangeInfo.",
    )
    parser.add_argument(
        "--session-name",
        type=str,
        default="manual_paper_session",
        help="Nome da sessão de paper trading.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="artifacts/paper_trading",
        help="Diretório de saída dos relatórios.",
    )
    parser.add_argument(
        "--initial-bankroll",
        type=float,
        default=2000.0,
        help="Bankroll inicial em USD para métricas.",
    )
    parser.add_argument(
        "--slippage-pct",
        type=float,
        default=0.0005,
        help="Slippage estimado usado na simulação.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.demo:
        features = build_demo_features()
        price_paths = build_demo_price_paths(features)
    else:
        if not args.features or not args.price_paths:
            raise SystemExit("Use --demo ou informe --features e --price-paths.")

        features = load_feature_snapshots(args.features)
        price_paths = load_price_paths(args.price_paths)

    rules = load_rules(args.rules)
    profile: RiskProfile = get_default_risk_profile()
    exposure = build_default_exposure(args.initial_bankroll)

    report = run_paper_trading_session(
        feature_snapshots=features,
        price_paths=price_paths,
        rules=rules,
        profile=profile,
        exposure_snapshot=exposure,
        session_name=args.session_name,
        estimated_slippage_pct=args.slippage_pct,
        initial_balance_usd=args.initial_bankroll,
    )

    paths = export_paper_trading_report(
        report,
        output_dir=args.output_dir,
    )

    print("Paper trading session completed")
    print(f"Session: {report.session_name}")
    print(f"Summary: {paths['summary']}")
    print(f"Trades: {paths['trades']}")
    print(json.dumps(report.metrics, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())