"""
Full backtest runner for Binance Futures.

Uso demo:

    python scripts/run_full_backtest.py --demo --session-name full_backtest_demo

Uso com arquivos:

    python scripts/run_full_backtest.py ^
        --features artifacts/datasets/features.jsonl ^
        --price-paths artifacts/datasets/price_paths.json ^
        --session-name backtest_001

Este script NÃO executa ordens reais.
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


from backtesting.full_backtest import (
    FullBacktestCostModel,
    export_full_backtest_report,
    run_full_backtest,
)
from risk.risk_manager import RiskProfile, get_default_risk_profile
from scripts.run_paper_trading_session import (
    build_default_exposure,
    build_demo_features,
    build_demo_price_paths,
    load_feature_snapshots,
    load_price_paths,
    load_rules,
)


def build_cost_model_from_args(args: argparse.Namespace) -> FullBacktestCostModel:
    return FullBacktestCostModel(
        taker_fee_rate=args.taker_fee_rate,
        maker_fee_rate=args.maker_fee_rate,
        spread_pct=args.spread_pct,
        slippage_pct=args.slippage_pct,
        latency_ms=args.latency_ms,
        funding_cost_usd=args.funding_cost_usd,
        partial_fill_ratio=args.partial_fill_ratio,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Binance Futures full backtest with realistic costs."
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
        default="full_backtest_session",
        help="Nome da sessão de full backtest.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="artifacts/full_backtest",
        help="Diretório de saída.",
    )
    parser.add_argument(
        "--initial-balance",
        type=float,
        default=2000.0,
        help="Saldo inicial em USD.",
    )
    parser.add_argument(
        "--slippage-pct",
        type=float,
        default=0.0005,
        help="Slippage estimado.",
    )
    parser.add_argument(
        "--spread-pct",
        type=float,
        default=0.0002,
        help="Spread médio estimado.",
    )
    parser.add_argument(
        "--latency-ms",
        type=int,
        default=200,
        help="Latência simulada em milissegundos.",
    )
    parser.add_argument(
        "--partial-fill-ratio",
        type=float,
        default=1.0,
        help="Percentual de fill simulado. Ex: 0.6 para 60%.",
    )
    parser.add_argument(
        "--taker-fee-rate",
        type=float,
        default=0.0005,
        help="Fee taker estimada Binance Futures.",
    )
    parser.add_argument(
        "--maker-fee-rate",
        type=float,
        default=0.0002,
        help="Fee maker estimada Binance Futures.",
    )
    parser.add_argument(
        "--funding-cost-usd",
        type=float,
        default=0.0,
        help="Custo de funding por trade em USD.",
    )

    return parser.parse_args()


def load_inputs(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    if args.demo:
        features = build_demo_features()
        price_paths = build_demo_price_paths(features)

        return features, price_paths

    if not args.features or not args.price_paths:
        raise SystemExit("Use --demo ou informe --features e --price-paths.")

    return load_feature_snapshots(args.features), load_price_paths(args.price_paths)


def main() -> int:
    args = parse_args()

    features, price_paths = load_inputs(args)

    rules = load_rules(args.rules)
    profile: RiskProfile = get_default_risk_profile()
    exposure = build_default_exposure(args.initial_balance)
    cost_model = build_cost_model_from_args(args)

    report = run_full_backtest(
        feature_snapshots=features,
        price_paths=price_paths,
        rules=rules,
        profile=profile,
        exposure_snapshot=exposure,
        session_name=args.session_name,
        initial_balance_usd=args.initial_balance,
        cost_model=cost_model,
    )

    paths = export_full_backtest_report(
        report,
        output_dir=args.output_dir,
        name=args.session_name,
    )

    print("Full backtest completed")
    print(f"Session: {args.session_name}")
    print(f"Summary: {paths['summary']}")
    print(f"Trades: {paths['trades']}")
    print(json.dumps(report.metrics, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())