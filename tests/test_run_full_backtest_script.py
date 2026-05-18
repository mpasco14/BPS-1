from scripts.run_full_backtest import (
    build_cost_model_from_args,
    load_inputs,
)
from argparse import Namespace


def test_build_cost_model_from_args():
    args = Namespace(
        taker_fee_rate=0.0005,
        maker_fee_rate=0.0002,
        spread_pct=0.0002,
        slippage_pct=0.0005,
        latency_ms=200,
        funding_cost_usd=0.0,
        partial_fill_ratio=0.75,
    )

    model = build_cost_model_from_args(args)

    assert model.taker_fee_rate == 0.0005
    assert model.partial_fill_ratio == 0.75
    assert model.latency_ms == 200


def test_load_inputs_demo():
    args = Namespace(
        demo=True,
        features=None,
        price_paths=None,
    )

    features, price_paths = load_inputs(args)

    assert len(features) == 3
    assert len(price_paths) == 3