from ops.sentiment_audit import SentimentAuditConfig, build_sentiment_audit_report, export_sentiment_audit_report
from sentiment.sentiment_schema import SentimentClassification, SentimentFeatureRow


def sample_classifications():
    return [
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
            score=0.0,
            confidence=0.5,
        ),
        SentimentClassification(
            item_id="3",
            source_type="reddit",
            source_name="reddit",
            sentiment="bearish",
            score=-0.4,
            confidence=0.6,
        ),
    ]


def test_sentiment_audit_passes():
    report = build_sentiment_audit_report(
        classifications=sample_classifications(),
        feature_row=SentimentFeatureRow(sentiment_confidence=0.7, items_count=3),
        config=SentimentAuditConfig(min_items=3),
    )

    assert report.passed is True
    assert report.items_count == 3


def test_sentiment_audit_blocks_low_items():
    report = build_sentiment_audit_report(
        classifications=sample_classifications()[:1],
        config=SentimentAuditConfig(min_items=3),
    )

    assert report.passed is False
    assert "sentiment_items_below_minimum" in report.blockers


def test_export_sentiment_audit_report(tmp_path):
    report = build_sentiment_audit_report(classifications=sample_classifications())

    path = export_sentiment_audit_report(
        report,
        output_dir=tmp_path,
        name="unit_audit",
    )

    assert path.exists()