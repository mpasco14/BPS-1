import json

import pytest

from execution.exit_dry_run_contract import (
    ExitReason,
    build_exit_dry_run_contract,
)
from execution.exit_dry_run_planner import (
    ExitDryRunPlanner,
    ExitDryRunPlannerInput,
)
from execution.exit_dry_run_reconciliation import (
    ExitDryRunReconciliationInput,
    ExitDryRunReconciler,
    ReconciliationStatus,
    write_exit_dry_run_reconciliation_report,
)


def _build_contract(
    *,
    current_position_size: float = 10.0,
    planned_exit_size: float = 4.0,
    reference_price: float | None = 0.62,
    estimated_fees: float = 0.10,
    estimated_slippage: float = 0.05,
):
    return build_exit_dry_run_contract(
        contract_id="dry-run-exit-test-001",
        market_id="btc-test-market",
        condition_id="condition-123",
        token_id="token-yes-123",
        side="YES",
        reason=ExitReason.MANUAL_DRY_RUN,
        current_position_size=current_position_size,
        planned_exit_size=planned_exit_size,
        reference_price=reference_price,
        estimated_fees=estimated_fees,
        estimated_slippage=estimated_slippage,
        risk_approved=False,
        kill_switch_active=False,
        metadata={"source": "unit-test"},
    )


def test_reconciler_generates_pass_report_for_valid_dry_run_exit():
    contract = _build_contract()
    reconciler = ExitDryRunReconciler()

    report = reconciler.reconcile(
        ExitDryRunReconciliationInput(
            contract=contract,
            starting_position_size=10.0,
            average_entry_price=0.50,
        )
    )

    data = report.to_dict()

    assert report.status == ReconciliationStatus.PASS
    assert report.passed is True
    assert data["status"] == "PASS"
    assert data["passed"] is True

    assert data["contract_id"] == "dry-run-exit-test-001"
    assert data["market_id"] == "btc-test-market"
    assert data["planned_exit_size"] == 4.0
    assert data["simulated_fill_size"] == 4.0
    assert data["remaining_position_size"] == 6.0

    assert data["simulated_exit_price"] == 0.62
    assert data["average_entry_price"] == 0.50

    assert data["gross_pnl"] == pytest.approx(0.48)
    assert data["net_pnl"] == pytest.approx(0.33)

    assert "contract is dry-run" in data["passed_checks"]
    assert "contract does not allow real execution" in data["passed_checks"]
    assert data["metadata"]["phase"] == "35.9"
    assert data["metadata"]["real_execution_allowed"] is False


def test_reconciler_skips_when_contract_has_no_exit_action():
    contract = _build_contract(
        current_position_size=0.0,
        planned_exit_size=0.0,
        reference_price=None,
        estimated_fees=0.0,
        estimated_slippage=0.0,
    )
    reconciler = ExitDryRunReconciler()

    report = reconciler.reconcile(
        ExitDryRunReconciliationInput(
            contract=contract,
            starting_position_size=0.0,
        )
    )

    data = report.to_dict()

    assert report.status == ReconciliationStatus.SKIPPED
    assert report.passed is False
    assert data["status"] == "SKIPPED"
    assert data["planned_exit_size"] == 0.0
    assert data["simulated_fill_size"] == 0.0
    assert data["remaining_position_size"] == 0.0
    assert data["gross_pnl"] == 0.0
    assert data["net_pnl"] == 0.0
    assert "contract planned no exit action" in data["notes"]


def test_reconciler_fails_when_starting_position_differs_from_contract():
    contract = _build_contract()
    reconciler = ExitDryRunReconciler()

    report = reconciler.reconcile(
        ExitDryRunReconciliationInput(
            contract=contract,
            starting_position_size=9.0,
            average_entry_price=0.50,
        )
    )

    data = report.to_dict()

    assert report.status == ReconciliationStatus.FAIL
    assert data["passed"] is False
    assert any(
        "starting_position_size differs" in check
        for check in data["failed_checks"]
    )


def test_reconciler_fails_when_simulated_fill_exceeds_planned_exit_size():
    contract = _build_contract()
    reconciler = ExitDryRunReconciler()

    report = reconciler.reconcile(
        ExitDryRunReconciliationInput(
            contract=contract,
            starting_position_size=10.0,
            simulated_fill_size=5.0,
            average_entry_price=0.50,
        )
    )

    data = report.to_dict()

    assert report.status == ReconciliationStatus.FAIL
    assert any(
        "simulated_fill_size exceeds planned_exit_size" in check
        for check in data["failed_checks"]
    )


def test_reconciler_fails_when_planned_exit_has_no_exit_price():
    contract = _build_contract(reference_price=None)
    reconciler = ExitDryRunReconciler()

    report = reconciler.reconcile(
        ExitDryRunReconciliationInput(
            contract=contract,
            starting_position_size=10.0,
            average_entry_price=0.50,
        )
    )

    data = report.to_dict()

    assert report.status == ReconciliationStatus.FAIL
    assert any(
        "simulated exit price is required" in check
        for check in data["failed_checks"]
    )


def test_reconciler_allows_missing_entry_price_but_pnl_is_unavailable():
    contract = _build_contract()
    reconciler = ExitDryRunReconciler()

    report = reconciler.reconcile(
        ExitDryRunReconciliationInput(
            contract=contract,
            starting_position_size=10.0,
        )
    )

    data = report.to_dict()

    assert report.status == ReconciliationStatus.PASS
    assert data["gross_pnl"] is None
    assert data["net_pnl"] is None
    assert any("pnl unavailable" in note for note in data["notes"])


def test_reconciler_rejects_negative_starting_position():
    contract = _build_contract()
    reconciler = ExitDryRunReconciler()

    with pytest.raises(ValueError, match="starting_position_size cannot be negative"):
        reconciler.reconcile(
            ExitDryRunReconciliationInput(
                contract=contract,
                starting_position_size=-1.0,
            )
        )


def test_reconciler_rejects_negative_simulated_fill_size():
    contract = _build_contract()
    reconciler = ExitDryRunReconciler()

    with pytest.raises(ValueError, match="simulated_fill_size cannot be negative"):
        reconciler.reconcile(
            ExitDryRunReconciliationInput(
                contract=contract,
                starting_position_size=10.0,
                simulated_fill_size=-1.0,
            )
        )


def test_reconciler_writes_json_report(tmp_path):
    contract = _build_contract()
    reconciler = ExitDryRunReconciler()

    report = reconciler.reconcile(
        ExitDryRunReconciliationInput(
            contract=contract,
            starting_position_size=10.0,
            average_entry_price=0.50,
        )
    )

    output_path = tmp_path / "exit_dry_run" / "reconciliation_report.json"

    written_path = write_exit_dry_run_reconciliation_report(
        report=report,
        output_path=output_path,
    )

    assert written_path == output_path
    assert written_path.exists()

    loaded = json.loads(written_path.read_text(encoding="utf-8"))

    assert loaded["status"] == "PASS"
    assert loaded["contract_id"] == "dry-run-exit-test-001"
    assert loaded["metadata"]["phase"] == "35.9"


def test_reconciler_integrates_with_exit_dry_run_planner():
    planner = ExitDryRunPlanner()
    reconciler = ExitDryRunReconciler()

    planner_result = planner.plan(
        ExitDryRunPlannerInput(
            market_id="btc-test-market",
            side="YES",
            current_position_size=2.0,
            reference_price=0.60,
            manual_dry_run=True,
            metadata={"source": "planner-integration-test"},
        )
    )

    assert planner_result.should_exit is True
    assert planner_result.contract is not None

    report = reconciler.reconcile(
        ExitDryRunReconciliationInput(
            contract=planner_result.contract,
            starting_position_size=2.0,
            average_entry_price=0.55,
        )
    )

    data = report.to_dict()

    assert report.status == ReconciliationStatus.PASS
    assert data["planned_exit_size"] == 2.0
    assert data["simulated_fill_size"] == 2.0
    assert data["remaining_position_size"] == 0.0
    assert data["gross_pnl"] == pytest.approx(0.10)
    assert data["metadata"]["phase"] == "35.9"
    assert data["metadata"]["planner"] == "ExitDryRunPlanner"
    assert data["metadata"]["reconciler"] == "ExitDryRunReconciler"
    assert data["metadata"]["real_execution_allowed"] is False