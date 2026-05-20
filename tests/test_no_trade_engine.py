from strategy.no_trade_engine import (
    NoTradeConfig,
    NoTradeInput,
    evaluate_no_trade,
    export_no_trade_decision,
)


def good_input():
    return NoTradeInput(
        model_confidence=0.72,
        expected_value_usd=0.5,
        spread_pct=0.0002,
        liquidity_usd=100000,
        regime="TRENDING_UP",
        risk_state_status="OK",
    )


def test_no_trade_allows_good_input():
    decision = evaluate_no_trade(
        input_data=good_input(),
        config=NoTradeConfig(),
    )

    assert decision.should_trade is True
    assert decision.action == "ALLOW_TRADE"


def test_no_trade_blocks_ood():
    data = good_input()
    data.model_ood = True

    decision = evaluate_no_trade(
        input_data=data,
        config=NoTradeConfig(),
    )

    assert decision.should_trade is False
    assert "model_ood_detected" in decision.blockers


def test_export_no_trade_decision(tmp_path):
    decision = evaluate_no_trade(input_data=good_input(), config=NoTradeConfig())

    path = export_no_trade_decision(
        decision,
        output_dir=tmp_path,
        name="unit_no_trade",
    )

    assert path.exists()