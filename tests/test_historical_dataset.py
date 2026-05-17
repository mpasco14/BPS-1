from pathlib import Path

from backtesting.backtest import price_path_key, run_backtest
from data.historical_dataset import (
    build_dataset_from_backtest_report,
    export_jsonl,
    load_jsonl,
    temporal_split,
)
from tests.test_backtest import custom_profile, sample_feature


def build_report():
    feature = sample_feature()
    key = price_path_key(feature)

    return run_backtest(
        feature_snapshots=[feature],
        price_paths={
            key: [
                {
                    "timestamp": "2026-05-15T18:05:00+00:00",
                    "high": 60300,
                    "low": 60000,
                    "close": 60300,
                },
            ]
        },
        profile=custom_profile(),
        initial_balance_usd=1000,
    )


def test_build_dataset_from_backtest_report():
    report = build_report()

    rows = build_dataset_from_backtest_report(report.model_dump(mode="json"))

    assert len(rows) == 1
    assert rows[0].symbol == "BTCUSDT"
    assert rows[0].side == "LONG"
    assert rows[0].target == 1
    assert rows[0].tech_score == 0.9
    assert rows[0].combined_score == 0.9


def test_temporal_split():
    rows = []

    for index in range(10):
        report = build_report()
        row = build_dataset_from_backtest_report(report.model_dump(mode="json"))[0]
        row.timestamp = f"2026-05-15T18:{index:02d}:00+00:00"
        rows.append(row)

    split = temporal_split(
        rows,
        train_ratio=0.7,
        validation_ratio=0.15,
        test_ratio=0.15,
    )

    assert len(split["train"]) == 7
    assert len(split["validation"]) == 1
    assert len(split["test"]) == 2


def test_export_and_load_jsonl(tmp_path: Path):
    report = build_report()
    rows = build_dataset_from_backtest_report(report.model_dump(mode="json"))

    path = export_jsonl(rows, tmp_path / "dataset.jsonl")
    loaded = load_jsonl(path)

    assert len(loaded) == 1
    assert loaded[0].symbol == "BTCUSDT"
    assert loaded[0].target == 1