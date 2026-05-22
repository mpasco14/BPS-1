from backtesting.sentiment_backtest import (
    SentimentBacktestConfig,
    SentimentBacktestSample,
    run_sentiment_backtest,
    export_sentiment_backtest_report,
)


def sample_backtest_data():
    return [
        SentimentBacktestSample(
            sentiment_features={
                "btc_sentiment_index": 70,
                "sentiment_confidence": 0.8,
            },
            future_return_pct=0.01,
        ),
        SentimentBacktestSample(
            sentiment_features={
                "btc_sentiment_index": 30,
                "sentiment_confidence": 0.8,
            },
            future_return_pct=-0.01,
        ),
        SentimentBacktestSample(
            sentiment_features={
                "btc_sentiment_index": 50,
                "sentiment_confidence": 0.8,
            },
            future_return_pct=0.01,
        ),
    ]


def test_run_sentiment_backtest():
    report = run_sentiment_backtest(
        samples=sample_backtest_data(),
        config=SentimentBacktestConfig(
            long_threshold=60,
            short_threshold=40,
            min_confidence=0.5,
            notional_usd=100,
            fee_rate=0.0,
        ),
    )

    assert report.samples_count == 3
    assert report.trades_count == 2
    assert report.hit_rate == 1.0
    assert report.net_pnl_usd == 2.0


def test_export_sentiment_backtest_report(tmp_path):
    report = run_sentiment_backtest(samples=sample_backtest_data())

    path = export_sentiment_backtest_report(
        report,
        output_dir=tmp_path,
        name="unit_sentiment_backtest",
    )

    assert path.exists()