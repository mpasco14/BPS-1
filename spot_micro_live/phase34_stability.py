from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from spot_micro_live.phase33b import (
    SpotMicroLiveConfig,
    decimal_floor_to_step,
    env_bool,
    env_float,
    env_int,
    export_json,
    filters_by_type,
    final_status,
    get_current_price,
    get_symbol_info,
    load_config as load_phase33b_config,
    load_json,
    run_spot_kill_switch,
    run_spot_readonly_snapshot,
    run_spot_reconciliation,
    run_spot_small_limit_order,
    sanitize_payload,
)

Status = Literal["PASS", "WARN", "FAIL"]
Decision = Literal["GO", "HOLD", "NO_GO"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Phase34StabilityConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/spot_brl_stability")

    iterations: int = 3
    cooldown_seconds: int = 10
    limit_price_offset_pct: float = 0.01

    baseline_base_free: float = 0.0
    baseline_quote_free: float = 0.0
    inventory_tolerance_base: float = 0.00000001

    require_phase33b_session_report: bool = True
    phase33b_session_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_micro_live_session_report.json"
    )

    allow_real_repeat: bool = False
    allow_emergency_cancel_all: bool = False
    confirmation_phrase: str = ""

    stop_on_fill: bool = True
    max_allowed_fills: int = 0
    require_open_orders_zero: bool = True
    require_final_reconciliation: bool = True


class Phase34GateReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    generated_at: datetime = Field(default_factory=utc_now)
    status: Status
    passed: bool
    decision: Decision
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepeatSubmitCancelReport(Phase34GateReport):
    source: str = "spot_brl_repeat_micro_live_submit_cancel_x3"

    iterations_requested: int
    iterations_completed: int
    submitted_count: int
    cancel_passed_count: int
    fill_count: int
    final_reconciled_count: int

    open_orders_count_after: int | None = None
    quote_free_after: float | None = None
    quote_locked_after: float | None = None
    base_free_after: float | None = None
    base_locked_after: float | None = None

    baseline_base_free: float = 0.0
    baseline_quote_free: float = 0.0
    base_free_delta_after: float | None = None
    quote_free_delta_after: float | None = None
    inventory_delta_detected: bool = False

    iteration_reports: list[dict[str, Any]] = Field(default_factory=list)


class ReconciliationAuditReport(Phase34GateReport):
    source: str = "spot_brl_post_order_reconciliation_audit"

    open_orders_count: int
    base_free: float
    base_locked: float
    quote_free: float
    quote_locked: float
    final_reconciled: bool


class FeeDustAccountingReport(Phase34GateReport):
    source: str = "spot_brl_fee_dust_accounting"

    base_free: float
    base_locked: float
    quote_free: float
    quote_locked: float

    baseline_base_free: float = 0.0
    baseline_quote_free: float = 0.0
    base_free_delta: float = 0.0
    quote_free_delta: float = 0.0

    inventory_detected: bool
    inventory_delta_detected: bool = False
    possible_dust_detected: bool


class FillRiskSlippageReviewReport(Phase34GateReport):
    source: str = "spot_brl_fill_risk_slippage_review"

    fill_count: int
    fill_detected: bool
    inventory_detected: bool
    inventory_delta_detected: bool = False

    base_free_after: float
    quote_free_after: float | None = None
    baseline_base_free: float = 0.0
    base_free_delta_after: float = 0.0

    stop_on_fill: bool
    max_allowed_fills: int


class EmergencyCancelAllDrillReport(Phase34GateReport):
    source: str = "spot_brl_emergency_cancel_all_drill"

    attempted: bool
    passed_drill: bool
    open_orders_after: int | None = None


class StabilityCampaignReport(Phase34GateReport):
    source: str = "spot_brl_micro_live_stability_campaign_report"

    repeat_passed: bool
    reconciliation_audit_passed: bool
    fee_dust_passed: bool
    fill_risk_passed: bool
    emergency_drill_passed: bool
    open_orders_count: int
    final_reconciled: bool


def load_phase34_config() -> Phase34StabilityConfig:
    return Phase34StabilityConfig(
        output_dir=Path(
            os.getenv("SPOT_STABILITY_OUTPUT_DIR", "artifacts/spot_brl_stability")
        ),
        iterations=env_int("SPOT_STABILITY_ITERATIONS", 3),
        cooldown_seconds=env_int("SPOT_STABILITY_COOLDOWN_SECONDS", 10),
        limit_price_offset_pct=env_float(
            "SPOT_STABILITY_LIMIT_PRICE_OFFSET_PCT",
            0.01,
        ),
        baseline_base_free=env_float(
            "SPOT_STABILITY_BASELINE_BASE_FREE",
            0.0,
        ),
        baseline_quote_free=env_float(
            "SPOT_STABILITY_BASELINE_QUOTE_FREE",
            0.0,
        ),
        inventory_tolerance_base=env_float(
            "SPOT_STABILITY_INVENTORY_TOLERANCE_BASE",
            0.00000001,
        ),
        require_phase33b_session_report=env_bool(
            "SPOT_STABILITY_REQUIRE_PHASE33B_SESSION_REPORT",
            True,
        ),
        phase33b_session_report_path=Path(
            os.getenv(
                "SPOT_STABILITY_PHASE33B_SESSION_REPORT_PATH",
                "artifacts/spot_micro_live/spot_micro_live_session_report.json",
            )
        ),
        allow_real_repeat=env_bool("SPOT_STABILITY_ALLOW_REAL_REPEAT", False),
        allow_emergency_cancel_all=env_bool(
            "SPOT_STABILITY_ALLOW_EMERGENCY_CANCEL_ALL",
            False,
        ),
        confirmation_phrase=os.getenv("SPOT_STABILITY_CONFIRM_PHRASE", ""),
        stop_on_fill=env_bool("SPOT_STABILITY_STOP_ON_FILL", True),
        max_allowed_fills=env_int("SPOT_STABILITY_MAX_ALLOWED_FILLS", 0),
        require_open_orders_zero=env_bool(
            "SPOT_STABILITY_REQUIRE_OPEN_ORDERS_ZERO",
            True,
        ),
        require_final_reconciliation=env_bool(
            "SPOT_STABILITY_REQUIRE_FINAL_RECONCILIATION",
            True,
        ),
    )


def validate_phase33b_session(config: Phase34StabilityConfig) -> list[str]:
    if not config.require_phase33b_session_report:
        return []

    report = load_json(config.phase33b_session_report_path)

    if not report:
        return ["phase33b_session_report_missing"]

    if report.get("passed") is not True:
        return ["phase33b_session_report_not_passed"]

    if report.get("small_order_passed") is not True:
        return ["phase33b_small_order_not_confirmed"]

    if report.get("reconciliation_passed") is not True:
        return ["phase33b_reconciliation_not_confirmed"]

    if int(report.get("open_orders_count", 999)) != 0:
        return ["phase33b_open_orders_not_zero"]

    if report.get("final_reconciled") is not True:
        return ["phase33b_final_reconciliation_not_confirmed"]

    return []


def validate_repeat_unlock(config: Phase34StabilityConfig) -> list[str]:
    blockers = validate_phase33b_session(config)

    if config.iterations != 3:
        blockers.append("spot_stability_iterations_must_be_3_for_first_campaign")

    if not config.allow_real_repeat:
        blockers.append("spot_stability_real_repeat_not_allowed")

    if config.confirmation_phrase != "I_ACCEPT_SPOT_BRL_STABILITY_CAMPAIGN_RISK":
        blockers.append("spot_stability_confirmation_phrase_required")

    return blockers


def unlocked_phase33b_config() -> SpotMicroLiveConfig:
    base = load_phase33b_config()
    data = base.model_dump()

    data.update(
        {
            "spot_trading_enabled_declared": True,
            "allow_real_order_submission": True,
            "allow_real_cancel": True,
            "confirmation_phrase": "I_ACCEPT_SPOT_MICRO_LIVE_RISK",
        }
    )

    return SpotMicroLiveConfig(**data)


def locked_phase33b_config() -> SpotMicroLiveConfig:
    base = load_phase33b_config()
    data = base.model_dump()

    data.update(
        {
            "allow_real_order_submission": False,
            "allow_real_cancel": False,
            "confirmation_phrase": "",
        }
    )

    return SpotMicroLiveConfig(**data)


def offset_phase33b_config_for_submit_cancel(
    stability_config: Phase34StabilityConfig,
) -> SpotMicroLiveConfig:
    phase33b = unlocked_phase33b_config()

    symbol_info = get_symbol_info(phase33b)
    filters = filters_by_type(symbol_info)
    price_filter = filters.get("PRICE_FILTER", {})
    tick_size = price_filter.get("tickSize", "1.00000000")

    current_price = get_current_price(phase33b)
    offset = max(stability_config.limit_price_offset_pct, 0.0)

    if phase33b.side.upper() == "BUY":
        raw_price = current_price * (1.0 - offset)
    else:
        raw_price = current_price * (1.0 + offset)

    safe_price = decimal_floor_to_step(raw_price, tick_size)

    data = phase33b.model_dump()
    data.update(
        {
            "price": float(safe_price),
            "quantity": 0.0,
        }
    )

    return SpotMicroLiveConfig(**data)


def run_repeat_micro_live_submit_cancel_x3(
    config: Phase34StabilityConfig | None = None,
) -> RepeatSubmitCancelReport:
    resolved = config or load_phase34_config()

    blockers = validate_repeat_unlock(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []
    iteration_reports: list[dict[str, Any]] = []

    submitted_count = 0
    cancel_passed_count = 0
    fill_count = 0
    final_reconciled_count = 0

    open_orders_count_after = None
    quote_free_after = None
    quote_locked_after = None
    base_free_after = None
    base_locked_after = None

    base_free_delta_after = None
    quote_free_delta_after = None
    inventory_delta_detected = False

    if not blockers:
        for index in range(1, resolved.iterations + 1):
            iteration_config = offset_phase33b_config_for_submit_cancel(resolved)
            order_report = run_spot_small_limit_order(iteration_config)

            order_data = order_report.model_dump(mode="json")
            order_data["iteration"] = index
            order_data["limit_price_offset_pct"] = resolved.limit_price_offset_pct
            iteration_reports.append(sanitize_payload(order_data))

            if order_report.submitted:
                submitted_count += 1

            if order_report.cancel_passed:
                cancel_passed_count += 1

            if order_report.fill_detected:
                fill_count += 1

            if order_report.final_reconciled:
                final_reconciled_count += 1

            if order_report.passed is not True:
                blockers.append(f"iteration_{index}_small_order_not_passed")
                break

            if resolved.stop_on_fill and order_report.fill_detected:
                warnings.append(f"iteration_{index}_fill_detected_campaign_stopped")
                break

            if index < resolved.iterations:
                time.sleep(resolved.cooldown_seconds)

        reconciliation = run_spot_reconciliation(locked_phase33b_config())

        open_orders_count_after = reconciliation.open_orders_count
        quote_free_after = reconciliation.quote_free
        quote_locked_after = reconciliation.quote_locked
        base_free_after = reconciliation.base_free
        base_locked_after = reconciliation.base_locked

        if reconciliation.passed is not True:
            blockers.append("final_reconciliation_not_passed")

        if resolved.require_open_orders_zero and reconciliation.open_orders_count != 0:
            blockers.append("open_orders_remaining_after_campaign")

        if resolved.require_final_reconciliation and reconciliation.final_reconciled is not True:
            blockers.append("final_reconciliation_not_confirmed")

        if base_free_after is not None:
            base_free_delta_after = base_free_after - resolved.baseline_base_free
            inventory_delta_detected = (
                base_free_delta_after > resolved.inventory_tolerance_base
            )

        if quote_free_after is not None:
            quote_free_delta_after = quote_free_after - resolved.baseline_quote_free

        locked_balance_detected_after = (
            (base_locked_after or 0.0) > 0.0
            or (quote_locked_after or 0.0) > 0.0
        )

        if inventory_delta_detected:
            warnings.append("base_asset_inventory_delta_detected_after_campaign")
            fill_count = max(fill_count, 1)

        if locked_balance_detected_after:
            blockers.append("locked_balance_detected_after_campaign")

        if fill_count > resolved.max_allowed_fills:
            blockers.append("fill_count_above_allowed_limit")

    recommendations.append("Executar campanha x3 somente com saldo pequeno e flags temporárias.")
    recommendations.append("Interromper se houver fill, ordem aberta, saldo locked ou falha de cancelamento.")
    recommendations.append("Após campanha, submit/cancel devem voltar para OFF.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return RepeatSubmitCancelReport(
        status=status,
        passed=passed,
        decision=decision,
        iterations_requested=resolved.iterations,
        iterations_completed=len(iteration_reports),
        submitted_count=submitted_count,
        cancel_passed_count=cancel_passed_count,
        fill_count=fill_count,
        final_reconciled_count=final_reconciled_count,
        open_orders_count_after=open_orders_count_after,
        quote_free_after=quote_free_after,
        quote_locked_after=quote_locked_after,
        base_free_after=base_free_after,
        base_locked_after=base_locked_after,
        baseline_base_free=resolved.baseline_base_free,
        baseline_quote_free=resolved.baseline_quote_free,
        base_free_delta_after=base_free_delta_after,
        quote_free_delta_after=quote_free_delta_after,
        inventory_delta_detected=inventory_delta_detected,
        iteration_reports=iteration_reports,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def build_reconciliation_audit(
    config: Phase34StabilityConfig | None = None,
) -> ReconciliationAuditReport:
    _ = config or load_phase34_config()

    reconciliation = run_spot_reconciliation(locked_phase33b_config())

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if reconciliation.passed is not True:
        blockers.append("reconciliation_not_passed")

    if reconciliation.open_orders_count != 0:
        blockers.append("open_orders_detected")

    if reconciliation.base_locked > 0:
        blockers.append("base_locked_detected")

    if reconciliation.quote_locked > 0:
        warnings.append("quote_locked_detected_review_needed")

    if reconciliation.final_reconciled is not True:
        blockers.append("final_reconciled_false")

    recommendations.append("Audit deve confirmar open_orders=0 e locked balances zerados.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return ReconciliationAuditReport(
        status=status,
        passed=passed,
        decision=decision,
        open_orders_count=reconciliation.open_orders_count,
        base_free=reconciliation.base_free,
        base_locked=reconciliation.base_locked,
        quote_free=reconciliation.quote_free,
        quote_locked=reconciliation.quote_locked,
        final_reconciled=reconciliation.final_reconciled,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def build_fee_dust_accounting(
    config: Phase34StabilityConfig | None = None,
) -> FeeDustAccountingReport:
    resolved = config or load_phase34_config()

    readonly = run_spot_readonly_snapshot(locked_phase33b_config())

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if readonly.passed is not True:
        blockers.append("readonly_not_passed_for_fee_dust")

    base_free_delta = readonly.base_free - resolved.baseline_base_free
    quote_free_delta = readonly.quote_free - resolved.baseline_quote_free

    inventory_detected = readonly.base_free > 0.0
    inventory_delta_detected = base_free_delta > resolved.inventory_tolerance_base

    possible_dust = 0.0 < base_free_delta < 0.00001

    if inventory_delta_detected:
        blockers.append("base_asset_inventory_delta_detected_after_campaign")

    if possible_dust:
        warnings.append("possible_btc_dust_delta_detected")

    if readonly.base_locked > 0 or readonly.quote_locked > 0:
        blockers.append("locked_balance_detected")

    recommendations.append("Campanha submit/cancel sem novo fill deve terminar sem aumento de base_free.")
    recommendations.append("BTC residual anterior deve ser tratado como baseline, não como novo fill.")
    recommendations.append("Se base_free_delta > tolerância, registrar fill/inventory novo e revisar slippage.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return FeeDustAccountingReport(
        status=status,
        passed=passed,
        decision=decision,
        base_free=readonly.base_free,
        base_locked=readonly.base_locked,
        quote_free=readonly.quote_free,
        quote_locked=readonly.quote_locked,
        baseline_base_free=resolved.baseline_base_free,
        baseline_quote_free=resolved.baseline_quote_free,
        base_free_delta=base_free_delta,
        quote_free_delta=quote_free_delta,
        inventory_detected=inventory_detected,
        inventory_delta_detected=inventory_delta_detected,
        possible_dust_detected=possible_dust,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def build_fill_risk_slippage_review(
    config: Phase34StabilityConfig | None = None,
) -> FillRiskSlippageReviewReport:
    resolved = config or load_phase34_config()

    repeat_report = load_json(resolved.output_dir / "repeat_submit_cancel_x3.json")

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    fill_count = int(repeat_report.get("fill_count", 0)) if repeat_report else 0
    base_free_after = (
        float(repeat_report.get("base_free_after", 0.0) or 0.0)
        if repeat_report
        else 0.0
    )
    quote_free_after = repeat_report.get("quote_free_after") if repeat_report else None

    base_free_delta_after = base_free_after - resolved.baseline_base_free

    inventory_detected = base_free_after > 0.0
    inventory_delta_detected = (
        base_free_delta_after > resolved.inventory_tolerance_base
    )

    if not repeat_report:
        blockers.append("repeat_submit_cancel_report_missing")

    if inventory_delta_detected and fill_count == 0:
        fill_count = 1
        warnings.append("base_asset_inventory_delta_detected_but_fill_counter_was_zero")

    fill_detected = fill_count > 0 or inventory_delta_detected

    if fill_count > resolved.max_allowed_fills:
        blockers.append("fill_count_above_allowed_limit")

    if inventory_delta_detected:
        blockers.append("base_asset_inventory_delta_detected_after_campaign")

    if fill_detected:
        warnings.append("fill_or_inventory_delta_detected_review_slippage_and_fees")

    recommendations.append("Para campanha submit/cancel, fill_count esperado é zero.")
    recommendations.append("BTC residual anterior deve ser comparado contra baseline.")
    recommendations.append("Se base_free_after subir acima do baseline, tratar como novo fill.")
    recommendations.append("Antes de nova campanha, usar preço limite abaixo do mercado para BUY.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return FillRiskSlippageReviewReport(
        status=status,
        passed=passed,
        decision=decision,
        fill_count=fill_count,
        fill_detected=fill_detected,
        inventory_detected=inventory_detected,
        inventory_delta_detected=inventory_delta_detected,
        base_free_after=base_free_after,
        quote_free_after=quote_free_after,
        baseline_base_free=resolved.baseline_base_free,
        base_free_delta_after=base_free_delta_after,
        stop_on_fill=resolved.stop_on_fill,
        max_allowed_fills=resolved.max_allowed_fills,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def run_emergency_cancel_all_drill(
    config: Phase34StabilityConfig | None = None,
) -> EmergencyCancelAllDrillReport:
    resolved = config or load_phase34_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    attempted = False
    passed_drill = False
    open_orders_after = None

    if not resolved.allow_emergency_cancel_all:
        blockers.append("emergency_cancel_all_not_allowed")

    if resolved.confirmation_phrase != "I_ACCEPT_SPOT_BRL_STABILITY_CAMPAIGN_RISK":
        blockers.append("spot_stability_confirmation_phrase_required")

    if not blockers:
        phase33b = unlocked_phase33b_config()
        phase33b.allow_kill_switch = True

        attempted = True
        drill = run_spot_kill_switch(phase33b)
        passed_drill = drill.passed
        open_orders_after = drill.open_orders_after

        if drill.passed is not True:
            blockers.append("emergency_cancel_all_drill_not_passed")

        if open_orders_after not in {0, None}:
            blockers.append("open_orders_remaining_after_emergency_drill")

    recommendations.append("Drill deve ser usado apenas para validar cancel-all com saldo pequeno.")
    recommendations.append("Após drill, rodar reconciliation audit.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return EmergencyCancelAllDrillReport(
        status=status,
        passed=passed,
        decision=decision,
        attempted=attempted,
        passed_drill=passed_drill,
        open_orders_after=open_orders_after,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def build_stability_campaign_report(
    config: Phase34StabilityConfig | None = None,
) -> StabilityCampaignReport:
    resolved = config or load_phase34_config()

    repeat = load_json(resolved.output_dir / "repeat_submit_cancel_x3.json") or {}
    audit = load_json(resolved.output_dir / "post_order_reconciliation_audit.json") or {}
    fee_dust = load_json(resolved.output_dir / "brl_fee_dust_accounting.json") or {}
    fill_risk = load_json(resolved.output_dir / "fill_risk_slippage_review.json") or {}
    emergency = load_json(resolved.output_dir / "emergency_cancel_all_drill.json") or {}

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    repeat_passed = repeat.get("passed") is True
    audit_passed = audit.get("passed") is True
    fee_dust_passed = fee_dust.get("passed") is True
    fill_risk_passed = fill_risk.get("passed") is True
    emergency_passed = emergency.get("passed") is True if emergency else False

    open_orders_count = int(audit.get("open_orders_count", 999))
    final_reconciled = bool(audit.get("final_reconciled", False))

    if not repeat_passed:
        blockers.append("repeat_submit_cancel_not_passed")

    if not audit_passed:
        blockers.append("reconciliation_audit_not_passed")

    if not fee_dust_passed:
        blockers.append("fee_dust_accounting_not_passed")

    if not fill_risk_passed:
        blockers.append("fill_risk_review_not_passed")

    if open_orders_count != 0:
        blockers.append("open_orders_detected")

    if not final_reconciled:
        blockers.append("final_reconciliation_not_confirmed")

    if emergency and not emergency_passed:
        warnings.append("emergency_drill_not_passed_or_not_executed")

    recommendations.append("Se campanha x3 passar sem fill, avançar para campanha com observabilidade ampliada.")
    recommendations.append("Não aumentar tamanho de ordem antes de revisar fees, dust e slippage.")
    recommendations.append("Manter withdrawals e internal transfer fora da API de trading.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return StabilityCampaignReport(
        status=status,
        passed=passed,
        decision=decision,
        repeat_passed=repeat_passed,
        reconciliation_audit_passed=audit_passed,
        fee_dust_passed=fee_dust_passed,
        fill_risk_passed=fill_risk_passed,
        emergency_drill_passed=emergency_passed,
        open_orders_count=open_orders_count,
        final_reconciled=final_reconciled,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )
