from ops.sentiment_audit import SentimentAuditConfig, build_sentiment_audit_report
from ops.sentiment_strategy_health import (
    SentimentStrategyHealthConfig,
    build_sentiment_strategy_health_report,
    export_sentiment_strategy_health_report,
)
from ops.strategy_health import StrategyHealthInput
from sentiment.sentiment_schema import SentimentClassification, SentimentFeatureRow


def healthy_strategy_input():
    return StrategyHealthInput(
        trades_count=50,
        net_pnl_usd=10,
        max_drawdown_pct=0.03,
        profit_factor=1.3,
        win_rate=0.58,
        fill_rate=0.75,
        rejection_rate=0.02,
        expected_calibration_error=0.08,
        ood_rate=0.05,
        discipline_score=0.95,
        risk_state_status="OK",
    )


def healthy_sentiment_row():
    return SentimentFeatureRow(
        btc_sentiment_index=65,
        fear_greed_value=65,
        fear_greed_label="greed",
        sentiment_confidence=0.8,
        items_count=5,
        bullish_count=3,
        bearish_count=1,
        neutral_count=1,
    )


def test_sentiment_strategy_health_healthy():
    report = build_sentiment_strategy_health_report(
        strategy_input=healthy_strategy_input(),
        sentiment_row=healthy_sentiment_row(),
        config=SentimentStrategyHealthConfig(),
    )

    assert report.status == "HEALTHY"
    assert report.passed is True


def test_sentiment_strategy_health_blocks_low_items():
    row = healthy_sentiment_row()
    row.items_count = 1

    report = build_sentiment_strategy_health_report(
        strategy_input=healthy_strategy_input(),
        sentiment_row=row,
        config=SentimentStrategyHealthConfig(min_items=3),
    )

    assert report.status == "BLOCKED"
    assert "sentiment_items_below_health_minimum" in report.blockers


def test_sentiment_strategy_health_with_audit(tmp_path):
    audit = build_sentiment_audit_report(
        classifications=[
            SentimentClassification(
                item_id="1",
                source_type="news",
                source_name="news",
                sentiment="bullish",
                score=0.8,
                confidence=0.9,
            ),
            SentimentClassification(
                item_id="2",
                source_type="x",
                source_name="x",
                sentiment="neutral",
                score=0,
                confidence=0.5,
            ),
            SentimentClassification(
                item_id="3",
                source_type="reddit",
                source_name="reddit",
                sentiment="bearish",
                score=-0.2,
                confidence=0.5,
            ),
        ],
        feature_row=healthy_sentiment_row(),
        config=SentimentAuditConfig(min_items=3),
    )

    report = build_sentiment_strategy_health_report(
        strategy_input=healthy_strategy_input(),
        sentiment_row=healthy_sentiment_row(),
        audit_report=audit,
    )

    path = export_sentiment_strategy_health_report(
        report,
        output_dir=tmp_path,
        name="unit_sentiment_health",
    )

    assert path.exists()