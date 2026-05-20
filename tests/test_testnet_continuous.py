from ops.testnet_continuous import (
    TestnetContinuousConfig,
    build_testnet_continuous_report,
    export_testnet_continuous_report,
)


def sample_summaries():
    return [
        {
            "metrics": {
                "filled_orders": 10,
                "fill_rate": 0.8,
                "rejection_rate": 0.0,
                "cancel_rate": 0.1,
                "net_pnl_usd": 1,
            }
        },
        {
            "metrics": {
                "filled_orders": 10,
                "fill_rate": 0.7,
                "rejection_rate": 0.0,
                "cancel_rate": 0.1,
                "net_pnl_usd": 2,
            }
        },
    ]


def test_build_testnet_continuous_report():
    report = build_testnet_continuous_report(
        summaries=sample_summaries(),
        config=TestnetContinuousConfig(
            min_sessions=2,
            min_trades=20,
            min_fill_rate=0.6,
        ),
    )

    assert report.passed is True
    assert report.sessions_count == 2
    assert report.trades_count == 20


def test_export_testnet_continuous_report(tmp_path):
    report = build_testnet_continuous_report(
        summaries=sample_summaries(),
        config=TestnetContinuousConfig(min_sessions=2, min_trades=20),
    )

    path = export_testnet_continuous_report(
        report,
        output_dir=tmp_path,
        name="unit_continuous",
    )

    assert path.exists()