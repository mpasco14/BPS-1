from sentiment.sentiment_schema import SentimentFeatureRow
from strategy.no_trade_engine import NoTradeInput
from strategy.sentiment_no_trade_adapter import (
    SentimentNoTradeConfig,
    evaluate_no_trade_with_sentiment,
    evaluate_sentiment_no_trade,
)


def test_sentiment_no_trade_passes_normal_sentiment():
    row = SentimentFeatureRow(
        btc_sentiment_index=65,
        fear_greed_value=65,
        fear_greed_label="greed",
        sentiment_confidence=0.8,
        items_count=5,
    )

    assessment = evaluate_sentiment_no_trade(
        sentiment_row=row,
        intended_side="LONG",
        config=SentimentNoTradeConfig(),
    )

    assert assessment.should_block is False


def test_sentiment_no_trade_blocks_extreme_greed_long():
    row = SentimentFeatureRow(
        btc_sentiment_index=90,
        fear_greed_value=90,
        fear_greed_label="extreme_greed",
        sentiment_confidence=0.8,
        euphoria_score=50,
        items_count=5,
    )

    assessment = evaluate_sentiment_no_trade(
        sentiment_row=row,
        intended_side="LONG",
        config=SentimentNoTradeConfig(),
    )

    assert assessment.should_block is True
    assert "sentiment_extreme_greed_blocks_long" in assessment.blockers


def test_evaluate_no_trade_with_sentiment_combines_blockers():
    row = SentimentFeatureRow(
        btc_sentiment_index=90,
        fear_greed_value=90,
        fear_greed_label="extreme_greed",
        sentiment_confidence=0.8,
        items_count=5,
    )

    decision = evaluate_no_trade_with_sentiment(
        base_input=NoTradeInput(
            model_confidence=0.72,
            expected_value_usd=0.5,
            spread_pct=0.0002,
            liquidity_usd=100000,
            regime="TRENDING_UP",
            risk_state_status="OK",
        ),
        sentiment_row=row,
        intended_side="LONG",
    )

    assert decision.should_trade is False
    assert "sentiment_extreme_greed_blocks_long" in decision.blockers