from system_integration.execution_contract import OrderPlan, RiskApprovalDecision, validate_execution_contract


def test_execution_contract_approves_dry_run_order():
    report = validate_execution_contract(
        order_plan=OrderPlan(
            order_plan_id="unit",
            side="BUY",
            quantity=0.001,
            price=60000,
            notional_usd=60,
            margin_usd=5,
            leverage=12,
            dry_run=True,
            idempotency_key="unit-key",
        ),
        risk_decision=RiskApprovalDecision(approved=True),
        execution_mode="paper",
    )

    assert report.approved is True
    assert report.status == "DRY_RUN_READY"


def test_execution_contract_blocks_missing_risk():
    report = validate_execution_contract(
        order_plan=OrderPlan(
            order_plan_id="unit",
            side="BUY",
            quantity=0.001,
            price=60000,
            notional_usd=60,
            margin_usd=5,
            leverage=12,
            idempotency_key="unit-key",
        ),
        risk_decision=None,
    )

    assert report.approved is False
    assert "risk_decision_missing" in report.blockers


def test_execution_contract_blocks_kill_switch():
    report = validate_execution_contract(
        order_plan=OrderPlan(
            order_plan_id="unit",
            side="BUY",
            quantity=0.001,
            price=60000,
            notional_usd=60,
            margin_usd=5,
            leverage=12,
            idempotency_key="unit-key",
        ),
        risk_decision=RiskApprovalDecision(approved=True),
        kill_switch_active=True,
    )

    assert report.approved is False
    assert "kill_switch_active_blocks_execution" in report.blockers