from datetime import datetime, timedelta, timezone

from ops.data_quality_gate import (
    DataQualityConfig,
    DataQualityInput,
    evaluate_data_quality,
    export_data_quality_report,
)


def good_input():
    now = datetime.now(timezone.utc)

    return DataQualityInput(
        now=now,
        symbol="BTCUSDT",
        timeframe="5m",
        candle_timestamp=now,
        orderbook_timestamp=now,
        last_price=60000,
        reference_price=60001,
        spread_pct=0.0002,
        liquidity_usd=100000,
        websocket_connected=True,
        orderbook_tradeable=True,
        missing_features=[],
        feature_values={"technical_score": 0.7},
    )


def test_data_quality_passes_good_input():
    report = evaluate_data_quality(
        data=good_input(),
        config=DataQualityConfig(),
    )

    assert report.passed is True


def test_data_quality_blocks_stale_candle():
    data = good_input()
    data.candle_timestamp = data.now - timedelta(seconds=1000)

    report = evaluate_data_quality(
        data=data,
        config=DataQualityConfig(max_candle_age_seconds=120),
    )

    assert report.passed is False
    assert "CANDLE_STALE_OR_MISSING" in report.blockers


def test_export_data_quality_report(tmp_path):
    report = evaluate_data_quality(
        data=good_input(),
        config=DataQualityConfig(),
    )

    path = export_data_quality_report(
        report,
        output_dir=tmp_path,
        name="unit_data_quality",
    )

    assert path.exists()