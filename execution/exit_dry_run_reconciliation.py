from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from execution.exit_dry_run_contract import ExitDryRunContract


class ReconciliationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class ExitDryRunReconciliationInput:
    """
    Input used to reconcile a dry-run exit contract.

    This object is intentionally exchange-agnostic.
    It must contain only simulated values or values already known by
    previous safe layers of the system.

    It must never trigger balance reads, order submissions, order cancels,
    or real inventory changes.
    """

    contract: ExitDryRunContract
    starting_position_size: float

    simulated_fill_size: float | None = None
    simulated_exit_price: float | None = None

    average_entry_price: float | None = None

    simulated_fees: float | None = None
    simulated_slippage: float | None = None

    allow_position_flip: bool = False

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExitDryRunReconciliationReport:
    """
    Audit-friendly dry-run reconciliation report.

    The report describes what would have happened after the dry-run exit.
    It is safe to serialize, save, inspect in tests, or send to monitoring.

    It must not be used as proof that a real order was sent.
    """

    report_id: str
    generated_at: datetime

    contract_id: str
    market_id: str
    side: str
    action: str
    reason: str

    status: ReconciliationStatus

    starting_position_size: float
    contract_position_size: float
    planned_exit_size: float
    simulated_fill_size: float
    remaining_position_size: float

    reference_price: float | None
    simulated_exit_price: float | None
    average_entry_price: float | None

    estimated_fees: float
    estimated_slippage: float
    simulated_fees: float
    simulated_slippage: float

    gross_pnl: float | None
    net_pnl: float | None

    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == ReconciliationStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "contract_id": self.contract_id,
            "market_id": self.market_id,
            "side": self.side,
            "action": self.action,
            "reason": self.reason,
            "status": self.status.value,
            "passed": self.passed,
            "starting_position_size": self.starting_position_size,
            "contract_position_size": self.contract_position_size,
            "planned_exit_size": self.planned_exit_size,
            "simulated_fill_size": self.simulated_fill_size,
            "remaining_position_size": self.remaining_position_size,
            "reference_price": self.reference_price,
            "simulated_exit_price": self.simulated_exit_price,
            "average_entry_price": self.average_entry_price,
            "estimated_fees": self.estimated_fees,
            "estimated_slippage": self.estimated_slippage,
            "simulated_fees": self.simulated_fees,
            "simulated_slippage": self.simulated_slippage,
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "notes": self.notes,
            "metadata": self.metadata,
        }


class ExitDryRunReconciler:
    """
    Reconciles an ExitDryRunContract into an audit-friendly report.

    Safety rule:
    this reconciler only computes simulated post-exit state.
    It does not execute, cancel, modify, or route real orders.
    """

    def reconcile(
        self,
        reconciliation_input: ExitDryRunReconciliationInput,
    ) -> ExitDryRunReconciliationReport:
        self._validate_input(reconciliation_input)

        contract = reconciliation_input.contract
        contract.validate_safety()

        contract_data = contract.to_dict()

        planned_exit_size = contract.planned_exit_size
        simulated_fill_size = self._resolve_simulated_fill_size(
            reconciliation_input=reconciliation_input,
        )
        simulated_exit_price = self._resolve_simulated_exit_price(
            reconciliation_input=reconciliation_input,
        )
        simulated_fees = self._resolve_simulated_fees(
            reconciliation_input=reconciliation_input,
        )
        simulated_slippage = self._resolve_simulated_slippage(
            reconciliation_input=reconciliation_input,
        )

        remaining_position_size = (
            reconciliation_input.starting_position_size - simulated_fill_size
        )

        passed_checks: list[str] = []
        failed_checks: list[str] = []
        notes: list[str] = [
            "dry-run reconciliation only",
            "no real order submitted",
            "no real order cancelled",
            "no real balance mutated",
        ]

        self._run_reconciliation_checks(
            reconciliation_input=reconciliation_input,
            simulated_fill_size=simulated_fill_size,
            simulated_exit_price=simulated_exit_price,
            remaining_position_size=remaining_position_size,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            notes=notes,
        )

        gross_pnl, net_pnl = self._calculate_pnl(
            fill_size=simulated_fill_size,
            exit_price=simulated_exit_price,
            average_entry_price=reconciliation_input.average_entry_price,
            simulated_fees=simulated_fees,
            simulated_slippage=simulated_slippage,
            notes=notes,
        )

        status = self._resolve_status(
            planned_exit_size=planned_exit_size,
            failed_checks=failed_checks,
        )

        return ExitDryRunReconciliationReport(
            report_id=self._build_report_id(contract.contract_id),
            generated_at=datetime.now(timezone.utc),
            contract_id=contract.contract_id,
            market_id=contract.market_id,
            side=contract.side,
            action=contract.action,
            reason=contract.reason.value,
            status=status,
            starting_position_size=reconciliation_input.starting_position_size,
            contract_position_size=contract.current_position_size,
            planned_exit_size=planned_exit_size,
            simulated_fill_size=simulated_fill_size,
            remaining_position_size=remaining_position_size,
            reference_price=contract.reference_price,
            simulated_exit_price=simulated_exit_price,
            average_entry_price=reconciliation_input.average_entry_price,
            estimated_fees=contract.estimated_fees,
            estimated_slippage=contract.estimated_slippage,
            simulated_fees=simulated_fees,
            simulated_slippage=simulated_slippage,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            notes=notes,
            metadata={
                **contract_data.get("metadata", {}),
                **reconciliation_input.metadata,
                "phase": "35.9",
                "reconciler": "ExitDryRunReconciler",
                "real_execution_allowed": False,
            },
        )

    def _validate_input(
        self,
        reconciliation_input: ExitDryRunReconciliationInput,
    ) -> None:
        if reconciliation_input.starting_position_size < 0:
            raise ValueError("starting_position_size cannot be negative.")

        if (
            reconciliation_input.simulated_fill_size is not None
            and reconciliation_input.simulated_fill_size < 0
        ):
            raise ValueError("simulated_fill_size cannot be negative.")

        if (
            reconciliation_input.simulated_exit_price is not None
            and reconciliation_input.simulated_exit_price < 0
        ):
            raise ValueError("simulated_exit_price cannot be negative.")

        if (
            reconciliation_input.average_entry_price is not None
            and reconciliation_input.average_entry_price < 0
        ):
            raise ValueError("average_entry_price cannot be negative.")

        if (
            reconciliation_input.simulated_fees is not None
            and reconciliation_input.simulated_fees < 0
        ):
            raise ValueError("simulated_fees cannot be negative.")

        if (
            reconciliation_input.simulated_slippage is not None
            and reconciliation_input.simulated_slippage < 0
        ):
            raise ValueError("simulated_slippage cannot be negative.")

    def _resolve_simulated_fill_size(
        self,
        reconciliation_input: ExitDryRunReconciliationInput,
    ) -> float:
        if reconciliation_input.simulated_fill_size is not None:
            return reconciliation_input.simulated_fill_size

        return reconciliation_input.contract.planned_exit_size

    def _resolve_simulated_exit_price(
        self,
        reconciliation_input: ExitDryRunReconciliationInput,
    ) -> float | None:
        if reconciliation_input.simulated_exit_price is not None:
            return reconciliation_input.simulated_exit_price

        return reconciliation_input.contract.reference_price

    def _resolve_simulated_fees(
        self,
        reconciliation_input: ExitDryRunReconciliationInput,
    ) -> float:
        if reconciliation_input.simulated_fees is not None:
            return reconciliation_input.simulated_fees

        return reconciliation_input.contract.estimated_fees

    def _resolve_simulated_slippage(
        self,
        reconciliation_input: ExitDryRunReconciliationInput,
    ) -> float:
        if reconciliation_input.simulated_slippage is not None:
            return reconciliation_input.simulated_slippage

        return reconciliation_input.contract.estimated_slippage

    def _run_reconciliation_checks(
        self,
        *,
        reconciliation_input: ExitDryRunReconciliationInput,
        simulated_fill_size: float,
        simulated_exit_price: float | None,
        remaining_position_size: float,
        passed_checks: list[str],
        failed_checks: list[str],
        notes: list[str],
    ) -> None:
        contract = reconciliation_input.contract

        if contract.dry_run is True:
            passed_checks.append("contract is dry-run")
        else:
            failed_checks.append("contract is not dry-run")

        if contract.allow_real_execution is False:
            passed_checks.append("contract does not allow real execution")
        else:
            failed_checks.append("contract allows real execution")

        if reconciliation_input.starting_position_size == contract.current_position_size:
            passed_checks.append("starting position matches contract position")
        else:
            failed_checks.append(
                "starting_position_size differs from contract.current_position_size"
            )

        if simulated_fill_size <= contract.planned_exit_size:
            passed_checks.append("simulated fill size does not exceed planned exit size")
        else:
            failed_checks.append("simulated_fill_size exceeds planned_exit_size")

        if reconciliation_input.allow_position_flip:
            passed_checks.append("position flip explicitly allowed")
        elif remaining_position_size >= 0:
            passed_checks.append("remaining position is non-negative")
        else:
            failed_checks.append("remaining_position_size cannot be negative")

        if contract.planned_exit_size <= 0:
            notes.append("contract planned no exit action")
        elif simulated_exit_price is None:
            failed_checks.append("simulated exit price is required for planned exit")
        else:
            passed_checks.append("simulated exit price is available")

        if reconciliation_input.average_entry_price is None:
            notes.append("average_entry_price not provided; pnl fields may be unavailable")

    def _calculate_pnl(
        self,
        *,
        fill_size: float,
        exit_price: float | None,
        average_entry_price: float | None,
        simulated_fees: float,
        simulated_slippage: float,
        notes: list[str],
    ) -> tuple[float | None, float | None]:
        if fill_size <= 0:
            return 0.0, 0.0

        if exit_price is None or average_entry_price is None:
            notes.append("pnl unavailable because exit price or entry price is missing")
            return None, None

        gross_pnl = (exit_price - average_entry_price) * fill_size
        net_pnl = gross_pnl - simulated_fees - simulated_slippage

        return gross_pnl, net_pnl

    def _resolve_status(
        self,
        *,
        planned_exit_size: float,
        failed_checks: list[str],
    ) -> ReconciliationStatus:
        if failed_checks:
            return ReconciliationStatus.FAIL

        if planned_exit_size <= 0:
            return ReconciliationStatus.SKIPPED

        return ReconciliationStatus.PASS

    def _build_report_id(self, contract_id: str) -> str:
        return f"reconciliation-{contract_id}"


def write_exit_dry_run_reconciliation_report(
    report: ExitDryRunReconciliationReport,
    output_path: str | Path,
) -> Path:
    """
    Writes the dry-run reconciliation report to disk as JSON.

    This function only writes an audit artifact.
    It must not be used to trigger execution or mutate trading state.
    """

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return path