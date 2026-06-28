import pytest

from execution.exit_dry_run_contract import (
    ExitReason,
    build_exit_dry_run_contract,
)


def test_exit_dry_run_contract_is_always_safe():
    contract = build_exit_dry_run_contract(
        contract_id="dry-run-exit-001",
        market_id="btc-test-market",
        condition_id="condition-123",
        token_id="token-yes-123",
        side="YES",
        reason=ExitReason.KILL_SWITCH_TRIGGERED,
        current_position_size=10.0,
        planned_exit_size=4.0,
        reference_price=0.61,
        max_slippage_bps=50,
        estimated_fees=0.01,
        estimated_slippage=0.02,
        risk_approved=True,
        kill_switch_active=True,
        notes=["dry-run only", "no real order submitted"],
        metadata={"phase": "35.7"},
    )

    data = contract.to_dict()

    assert data["dry_run"] is True
    assert data["allow_real_execution"] is False
    assert data["action"] == "SELL_YES"
    assert data["reason"] == "KILL_SWITCH_TRIGGERED"
    assert data["planned_exit_size"] == 4.0
    assert data["current_position_size"] == 10.0


def test_exit_dry_run_contract_for_no_position_generates_no_action():
    contract = build_exit_dry_run_contract(
        contract_id="dry-run-exit-002",
        market_id="btc-test-market",
        side="NO",
        reason=ExitReason.RESIDUAL_INVENTORY_DETECTED,
        current_position_size=0.0,
        planned_exit_size=0.0,
    )

    data = contract.to_dict()

    assert data["action"] == "NO_ACTION"
    assert data["dry_run"] is True
    assert data["allow_real_execution"] is False


def test_exit_dry_run_contract_rejects_exit_size_above_position():
    with pytest.raises(ValueError, match="planned_exit_size cannot exceed current_position_size"):
        build_exit_dry_run_contract(
            contract_id="dry-run-exit-003",
            market_id="btc-test-market",
            side="YES",
            reason=ExitReason.MANUAL_DRY_RUN,
            current_position_size=1.0,
            planned_exit_size=2.0,
        )


def test_exit_dry_run_contract_rejects_negative_position():
    with pytest.raises(ValueError, match="current_position_size cannot be negative"):
        build_exit_dry_run_contract(
            contract_id="dry-run-exit-004",
            market_id="btc-test-market",
            side="YES",
            reason=ExitReason.MANUAL_DRY_RUN,
            current_position_size=-1.0,
            planned_exit_size=0.0,
        )


def test_exit_dry_run_contract_rejects_negative_slippage_bps():
    with pytest.raises(ValueError, match="max_slippage_bps cannot be negative"):
        build_exit_dry_run_contract(
            contract_id="dry-run-exit-005",
            market_id="btc-test-market",
            side="NO",
            reason=ExitReason.EDGE_DISAPPEARED,
            current_position_size=1.0,
            planned_exit_size=1.0,
            max_slippage_bps=-1,
        )