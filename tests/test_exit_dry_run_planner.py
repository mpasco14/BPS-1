import pytest

from execution.exit_dry_run_contract import ExitReason
from execution.exit_dry_run_planner import (
    ExitDryRunPlanner,
    ExitDryRunPlannerInput,
)


def test_planner_returns_no_exit_when_no_condition_is_triggered():
    planner = ExitDryRunPlanner()

    result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            side="YES",
            current_position_size=10.0,
            reference_price=0.55,
            current_edge=0.05,
            min_edge=0.02,
            time_to_expiry_seconds=3600,
        )
    )

    assert result.should_exit is False
    assert result.reason is None
    assert result.contract is None
    assert "No dry-run exit condition was triggered." in result.notes


def test_planner_generates_kill_switch_exit_contract():
    planner = ExitDryRunPlanner()

    result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            condition_id="condition-123",
            token_id="token-yes-123",
            side="YES",
            current_position_size=10.0,
            reference_price=0.61,
            kill_switch_active=True,
            metadata={"source": "unit-test"},
        )
    )

    assert result.should_exit is True
    assert result.reason == ExitReason.KILL_SWITCH_TRIGGERED
    assert result.contract is not None

    data = result.contract.to_dict()

    assert data["dry_run"] is True
    assert data["allow_real_execution"] is False
    assert data["market_id"] == "btc-test-market"
    assert data["condition_id"] == "condition-123"
    assert data["token_id"] == "token-yes-123"
    assert data["side"] == "YES"
    assert data["action"] == "SELL_YES"
    assert data["reason"] == "KILL_SWITCH_TRIGGERED"
    assert data["current_position_size"] == 10.0
    assert data["planned_exit_size"] == 10.0
    assert data["reference_price"] == 0.61
    assert data["kill_switch_active"] is True
    assert data["risk_approved"] is False
    assert data["metadata"]["phase"] == "35.8"
    assert data["metadata"]["real_execution_allowed"] is False


def test_planner_generates_residual_inventory_exit_contract():
    planner = ExitDryRunPlanner()

    result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            side="NO",
            current_position_size=3.0,
            reference_price=0.44,
            residual_inventory_detected=True,
        )
    )

    assert result.should_exit is True
    assert result.reason == ExitReason.RESIDUAL_INVENTORY_DETECTED
    assert result.contract is not None

    data = result.contract.to_dict()

    assert data["action"] == "SELL_NO"
    assert data["reason"] == "RESIDUAL_INVENTORY_DETECTED"
    assert data["planned_exit_size"] == 3.0
    assert data["dry_run"] is True
    assert data["allow_real_execution"] is False


def test_planner_generates_edge_disappeared_exit_contract():
    planner = ExitDryRunPlanner()

    result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            side="YES",
            current_position_size=5.0,
            reference_price=0.52,
            current_edge=0.01,
            min_edge=0.02,
        )
    )

    assert result.should_exit is True
    assert result.reason == ExitReason.EDGE_DISAPPEARED
    assert result.contract is not None

    data = result.contract.to_dict()

    assert data["reason"] == "EDGE_DISAPPEARED"
    assert data["planned_exit_size"] == 5.0
    assert data["dry_run"] is True
    assert data["allow_real_execution"] is False


def test_planner_generates_near_expiry_exit_contract():
    planner = ExitDryRunPlanner()

    result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            side="NO",
            current_position_size=2.0,
            reference_price=0.37,
            time_to_expiry_seconds=30,
            min_time_to_expiry_seconds=60,
        )
    )

    assert result.should_exit is True
    assert result.reason == ExitReason.MARKET_EXPIRED_OR_NEAR_EXPIRY
    assert result.contract is not None

    data = result.contract.to_dict()

    assert data["reason"] == "MARKET_EXPIRED_OR_NEAR_EXPIRY"
    assert data["action"] == "SELL_NO"


def test_planner_generates_manual_dry_run_contract():
    planner = ExitDryRunPlanner()

    result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            side="YES",
            current_position_size=1.5,
            reference_price=0.49,
            manual_dry_run=True,
        )
    )

    assert result.should_exit is True
    assert result.reason == ExitReason.MANUAL_DRY_RUN
    assert result.contract is not None

    data = result.contract.to_dict()

    assert data["reason"] == "MANUAL_DRY_RUN"
    assert data["dry_run"] is True
    assert data["allow_real_execution"] is False


def test_planner_prioritizes_kill_switch_over_other_reasons():
    planner = ExitDryRunPlanner()

    result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            side="YES",
            current_position_size=4.0,
            kill_switch_active=True,
            residual_inventory_detected=True,
            max_drawdown_reached=True,
            current_edge=-0.10,
            min_edge=0.02,
            time_to_expiry_seconds=10,
            min_time_to_expiry_seconds=60,
            manual_dry_run=True,
        )
    )

    assert result.should_exit is True
    assert result.reason == ExitReason.KILL_SWITCH_TRIGGERED

    data = result.contract.to_dict()

    assert data["reason"] == "KILL_SWITCH_TRIGGERED"
    assert data["dry_run"] is True
    assert data["allow_real_execution"] is False


def test_planner_does_not_exit_when_position_is_zero():
    planner = ExitDryRunPlanner()

    result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            side="YES",
            current_position_size=0.0,
            kill_switch_active=True,
            residual_inventory_detected=True,
            manual_dry_run=True,
        )
    )

    assert result.should_exit is False
    assert result.reason is None
    assert result.contract is None


def test_planner_rejects_negative_position():
    planner = ExitDryRunPlanner()

    with pytest.raises(ValueError, match="current_position_size cannot be negative"):
        planner.plan(
            ExitDryRunPlannerInput(
                market_id="btc-test-market",
                side="YES",
                current_position_size=-1.0,
            )
        )


def test_planner_rejects_missing_market_id():
    planner = ExitDryRunPlanner()

    with pytest.raises(ValueError, match="market_id is required"):
        planner.plan(
            ExitDryRunPlannerInput(
                market_id="",
                side="YES",
                current_position_size=1.0,
            )
        )


def test_planner_result_to_dict_is_serializable_shape():
    planner = ExitDryRunPlanner()

    result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            side="YES",
            current_position_size=1.0,
            manual_dry_run=True,
        )
    )

    data = result.to_dict()

    assert data["should_exit"] is True
    assert data["reason"] == "MANUAL_DRY_RUN"
    assert data["contract"]["dry_run"] is True
    assert data["contract"]["allow_real_execution"] is False