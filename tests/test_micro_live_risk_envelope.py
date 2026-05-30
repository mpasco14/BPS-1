from micro_live.risk_envelope import MicroCapitalRiskEnvelopeConfig, evaluate_micro_capital_risk_envelope


def test_micro_capital_risk_envelope_passes_conservative_defaults():
    report = evaluate_micro_capital_risk_envelope(
        config=MicroCapitalRiskEnvelopeConfig(
            max_capital_usd=25,
            max_order_notional_usd=10,
            max_daily_loss_usd=2,
            max_leverage=3,
            max_orders_per_session=1,
        )
    )

    assert report.passed is True


def test_micro_capital_risk_envelope_blocks_high_leverage():
    report = evaluate_micro_capital_risk_envelope(
        config=MicroCapitalRiskEnvelopeConfig(
            max_capital_usd=25,
            max_order_notional_usd=10,
            max_daily_loss_usd=2,
            max_leverage=10,
            max_orders_per_session=1,
        )
    )

    assert report.passed is False
    assert "micro_live_leverage_above_limit" in report.blockers