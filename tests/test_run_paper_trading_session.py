import json
from pathlib import Path

from scripts.run_paper_trading_session import (
    build_default_exposure,
    build_demo_features,
    build_demo_price_paths,
    load_feature_snapshots,
    load_price_paths,
    load_rules,
    sample_symbol_info,
)


def test_build_demo_features():
    features = build_demo_features()

    assert len(features) == 3
    assert features[0]["symbol"] == "BTCUSDT"
    assert features[0]["expected_value_usd"] > 0


def test_build_demo_price_paths():
    features = build_demo_features()
    price_paths = build_demo_price_paths(features)

    assert len(price_paths) == 3

    first_key = next(iter(price_paths.keys()))

    assert first_key.startswith("BTCUSDT:5m:")
    assert isinstance(price_paths[first_key], list)


def test_build_default_exposure():
    exposure = build_default_exposure(2000)

    assert exposure.total_bankroll_usd == 2000
    assert exposure.daily_pnl_usd == 0
    assert exposure.open_positions == 0


def test_load_feature_snapshots_json(tmp_path: Path):
    path = tmp_path / "features.json"
    path.write_text(
        json.dumps(
            {
                "features": [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": "2026-05-15T18:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rows = load_feature_snapshots(path)

    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"


def test_load_feature_snapshots_jsonl(tmp_path: Path):
    path = tmp_path / "features.jsonl"
    path.write_text(
        '{"symbol":"BTCUSDT","timestamp":"2026-05-15T18:00:00+00:00"}\n',
        encoding="utf-8",
    )

    rows = load_feature_snapshots(path)

    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"


def test_load_price_paths(tmp_path: Path):
    path = tmp_path / "price_paths.json"
    path.write_text(
        json.dumps(
            {
                "BTCUSDT:5m:2026-05-15T18:00:00+00:00": [
                    {
                        "timestamp": "2026-05-15T18:05:00+00:00",
                        "high": 60500,
                        "low": 60000,
                        "close": 60500,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    paths = load_price_paths(path)

    assert len(paths) == 1
    assert list(paths.values())[0][0]["high"] == 60500


def test_load_rules_default():
    rules = load_rules(None)

    assert rules.symbol == "BTCUSDT"
    assert rules.tick_size > 0
    assert rules.step_size > 0


def test_sample_symbol_info():
    info = sample_symbol_info()

    assert info["symbol"] == "BTCUSDT"
    assert len(info["filters"]) >= 3