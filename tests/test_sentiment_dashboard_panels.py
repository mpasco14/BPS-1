from dashboard.sentiment_panels import (
    build_sentiment_dashboard_snapshot,
    export_sentiment_dashboard_snapshot,
    render_sentiment_dashboard_html,
)
from sentiment.sentiment_schema import SentimentFeatureRow


def test_build_sentiment_dashboard_snapshot():
    snapshot = build_sentiment_dashboard_snapshot(
        rows=[
            SentimentFeatureRow(
                btc_sentiment_index=70,
                fear_greed_value=70,
                fear_greed_label="greed",
                sentiment_confidence=0.8,
                items_count=3,
            )
        ]
    )

    assert snapshot.panels["sentiment_index"] == 70
    assert snapshot.history_count == 1


def test_render_sentiment_dashboard_html():
    snapshot = build_sentiment_dashboard_snapshot(rows=[])

    html = render_sentiment_dashboard_html(snapshot)

    assert "BTC Sentiment Dashboard" in html


def test_export_sentiment_dashboard_snapshot(tmp_path):
    snapshot = build_sentiment_dashboard_snapshot(rows=[])

    paths = export_sentiment_dashboard_snapshot(
        snapshot,
        output_dir=tmp_path,
        name="unit_dashboard",
    )

    assert paths["json"].exists()
    assert paths["html"].exists()