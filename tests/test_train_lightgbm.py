from data.historical_dataset import DatasetRow
from models.train_lightgbm import (
    default_params,
    lightgbm_available,
    train_lightgbm_model,
)


def make_row(index: int, target: int):
    score = 0.8 if target == 1 else -0.8

    return DatasetRow(
        timestamp=f"2026-05-15T18:{index:02d}:00+00:00",
        venue="binance_futures",
        symbol="BTCUSDT",
        timeframe="5m",
        side="LONG",
        target=target,
        outcome="take_profit" if target == 1 else "stop_loss",
        tech_score=score,
        microstructure_score=score,
        onchain_score=0.05 * score,
        sentiment_score=0.03 * score,
        combined_score=score,
        binance_spread_pct=0.0001,
        binance_liquidity_usd=100000,
        funding_rate=0.0001,
        open_interest=100000,
        mark_price=60000 + index,
    )


def test_default_params():
    params = default_params()

    assert params["objective"] == "binary"
    assert "n_estimators" in params


def test_lightgbm_is_available():
    assert lightgbm_available() is True


def test_train_lightgbm_model(tmp_path):
    rows = [make_row(index, index % 2) for index in range(24)]

    result = train_lightgbm_model(
        train_rows=rows[:16],
        validation_rows=rows[16:20],
        test_rows=rows[20:],
        feature_columns=["tech_score", "combined_score"],
        output_dir=tmp_path,
        register=False,
        params={
            "n_estimators": 10,
            "min_child_samples": 1,
            "num_leaves": 3,
        },
    )

    assert result.model_path
    assert result.metadata_path
    assert result.train_metrics["samples"] == 16
    assert result.validation_metrics["samples"] == 4
    assert result.test_metrics["samples"] == 4