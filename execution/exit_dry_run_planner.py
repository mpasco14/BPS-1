from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from execution.exit_dry_run_contract import (
    ExitDryRunContract,
    ExitReason,
    ExitSide,
    build_exit_dry_run_contract,
)


@dataclass(frozen=True)
class ExitDryRunPlannerInput:
    """
    Snapshot used by the dry-run exit planner.

    This input is intentionally detached from real exchanges.
    It must contain only already-known state, simulated state, or values
    passed by previous safe layers of the system.

    The planner must not fetch balances, submit orders, cancel orders,
    or contact any real execution API.
    """

    market_id: str
    side: ExitSide
    current_position_size: float

    condition_id: str | None = None
    token_id: str | None = None

    reference_price: float | None = None
    max_slippage_bps: int = 50
    estimated_fees: float = 0.0
    estimated_slippage: float = 0.0

    current_edge: float | None = None
    min_edge: float | None = None

    time_to_expiry_seconds: int | None = None
    min_time_to_expiry_seconds: int = 60

    kill_switch_active: bool = False
    residual_inventory_detected: bool = False
    max_drawdown_reached: bool = False
    manual_dry_run: bool = False

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExitDryRunPlannerResult:
    """
    Result produced by the planner.

    contract is None when the planner decides that no exit dry-run
    is needed for the provided input.
    """

    should_exit: bool
    reason: ExitReason | None
    contract: ExitDryRunContract | None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_exit": self.should_exit,
            "reason": self.reason.value if self.reason else None,
            "contract": self.contract.to_dict() if self.contract else None,
            "notes": self.notes,
        }


class ExitDryRunPlanner:
    """
    Integrates exit decision logic with ExitDryRunContract.

    Safety rule:
    this planner only generates a dry-run contract.
    It does not execute, cancel, modify, or route real orders.
    """

    def plan(self, planner_input: ExitDryRunPlannerInput) -> ExitDryRunPlannerResult:
        self._validate_input(planner_input)

        reason = self._choose_exit_reason(planner_input)

        if reason is None:
            return ExitDryRunPlannerResult(
                should_exit=False,
                reason=None,
                contract=None,
                notes=["No dry-run exit condition was triggered."],
            )

        planned_exit_size = self._calculate_planned_exit_size(
            current_position_size=planner_input.current_position_size,
            reason=reason,
        )

        notes = self._build_notes(planner_input=planner_input, reason=reason)

        contract = build_exit_dry_run_contract(
            contract_id=self._build_contract_id(planner_input.market_id),
            market_id=planner_input.market_id,
            condition_id=planner_input.condition_id,
            token_id=planner_input.token_id,
            side=planner_input.side,
            reason=reason,
            current_position_size=planner_input.current_position_size,
            planned_exit_size=planned_exit_size,
            reference_price=planner_input.reference_price,
            max_slippage_bps=planner_input.max_slippage_bps,
            estimated_fees=planner_input.estimated_fees,
            estimated_slippage=planner_input.estimated_slippage,
            risk_approved=False,
            kill_switch_active=planner_input.kill_switch_active,
            notes=notes,
            metadata={
                **planner_input.metadata,
                "phase": "35.8",
                "planner": "ExitDryRunPlanner",
                "real_execution_allowed": False,
            },
        )

        return ExitDryRunPlannerResult(
            should_exit=True,
            reason=reason,
            contract=contract,
            notes=notes,
        )

    def _validate_input(self, planner_input: ExitDryRunPlannerInput) -> None:
        if not planner_input.market_id:
            raise ValueError("market_id is required.")

        if planner_input.current_position_size < 0:
            raise ValueError("current_position_size cannot be negative.")

        if planner_input.max_slippage_bps < 0:
            raise ValueError("max_slippage_bps cannot be negative.")

        if planner_input.estimated_fees < 0:
            raise ValueError("estimated_fees cannot be negative.")

        if planner_input.estimated_slippage < 0:
            raise ValueError("estimated_slippage cannot be negative.")

        if planner_input.reference_price is not None and planner_input.reference_price < 0:
            raise ValueError("reference_price cannot be negative.")

        if (
            planner_input.time_to_expiry_seconds is not None
            and planner_input.time_to_expiry_seconds < 0
        ):
            raise ValueError("time_to_expiry_seconds cannot be negative.")

    def _choose_exit_reason(
        self,
        planner_input: ExitDryRunPlannerInput,
    ) -> ExitReason | None:
        """
        Priority order matters.

        Highest priority:
        1. kill switch
        2. max drawdown
        3. residual inventory
        4. near expiry
        5. edge disappeared
        6. manual dry-run
        """

        if planner_input.current_position_size == 0:
            return None

        if planner_input.kill_switch_active:
            return ExitReason.KILL_SWITCH_TRIGGERED

        if planner_input.max_drawdown_reached:
            return ExitReason.MAX_DRAWDOWN_REACHED

        if planner_input.residual_inventory_detected:
            return ExitReason.RESIDUAL_INVENTORY_DETECTED

        if (
            planner_input.time_to_expiry_seconds is not None
            and planner_input.time_to_expiry_seconds
            <= planner_input.min_time_to_expiry_seconds
        ):
            return ExitReason.MARKET_EXPIRED_OR_NEAR_EXPIRY

        if (
            planner_input.current_edge is not None
            and planner_input.min_edge is not None
            and planner_input.current_edge < planner_input.min_edge
        ):
            return ExitReason.EDGE_DISAPPEARED

        if planner_input.manual_dry_run:
            return ExitReason.MANUAL_DRY_RUN

        return None

    def _calculate_planned_exit_size(
        self,
        *,
        current_position_size: float,
        reason: ExitReason,
    ) -> float:
        """
        For phase 35.8 we keep the exit sizing conservative and simple:
        if an exit reason exists, the dry-run plans to exit the full position.

        This is only a simulation. Real partial sizing can be introduced
        in a later phase.
        """

        if current_position_size <= 0:
            return 0.0

        return current_position_size

    def _build_notes(
        self,
        *,
        planner_input: ExitDryRunPlannerInput,
        reason: ExitReason,
    ) -> list[str]:
        notes = [
            "dry-run planner integration only",
            "no real order submitted",
            "no real order cancelled",
            f"exit reason selected: {reason.value}",
        ]

        if planner_input.current_edge is not None:
            notes.append(f"current_edge={planner_input.current_edge}")

        if planner_input.min_edge is not None:
            notes.append(f"min_edge={planner_input.min_edge}")

        if planner_input.time_to_expiry_seconds is not None:
            notes.append(
                f"time_to_expiry_seconds={planner_input.time_to_expiry_seconds}"
            )

        return notes

    def _build_contract_id(self, market_id: str) -> str:
        safe_market_id = market_id.replace(" ", "-")
        return f"exit-dry-run-{safe_market_id}-{uuid4().hex[:12]}"