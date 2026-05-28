from system_integration.execution_contract import RiskApprovalDecision
from system_integration.signal_risk_execution_adapter import SignalDecision, adapt_signal_to_risk_execution


def test_signal_risk_execution_adapter_approves_good_dry_run():
    result = adapt_signal_to_risk_execution(
        signal=SignalDecision(
            direction="BUY",
            confidence=0.7,
            edge=0.02,
            suggested_quantity=0.001,
            suggested_price=60000,
            suggested_notional_usd=60,
            suggested_margin_usd=5,
            suggested_leverage=12,
        ),
        risk_decision=RiskApprovalDecision(approved=True),
    )

    assert result.approved is True
    assert result.order_plan is not None


def test_signal_risk_execution_adapter_blocks_low_confidence():
    result = adapt_signal_to_risk_execution(
        signal=SignalDecision(
            direction="BUY",
            confidence=0.2,
            edge=0.02,
            suggested_quantity=0.001,
            suggested_price=60000,
            suggested_notional_usd=60,
            suggested_margin_usd=5,
        ),
        risk_decision=RiskApprovalDecision(approved=True),
    )

    assert result.approved is False
    assert "signal_confidence_below_minimum" in result.blockers