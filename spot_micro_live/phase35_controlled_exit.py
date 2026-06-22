from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from spot_micro_live.phase33b import (
    SpotMicroLiveConfig,
    env_bool,
    env_float,
    export_json,
    final_status,
    get_current_price,
    load_config as load_phase33b_config,
    load_json,
    run_spot_kill_switch,
    run_spot_readonly_snapshot,
)

Status = Literal["PASS", "WARN", "FAIL"]
Decision = Literal["GO", "HOLD", "NO_GO"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ControlledExitConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/spot_controlled_exit")

    symbol: str = "BTCBRL"
    base_asset: str = "BTC"
    quote_asset: str = "BRL"

    base_free_baseline: float = 0.00003996
    quote_free_baseline: float = 17.00184
    entry_executed_qty: float = 0.00004000
    entry_cumulative_quote_qty: float = 12.99816000

    policy: str = "MANUAL_ONLY"

    allow_real_sell: bool = False
    allow_cancel: bool = False
    confirmation_phrase: str = ""
    allow_kill_switch: bool = False
    kill_switch_confirmation_phrase: str = ""

    max_sell_base_qty: float = 0.00004
    min_expected_quote_brl: float = 10.0
    max_acceptable_loss_brl: float = 2.0
    require_open_orders_zero: bool = True
    require_no_locked_balance: bool = True

    fee_rate: float = 0.001
    spread_buffer_pct: float = 0.002
    min_net_pnl_brl: float = 0.0

    plan_path: Path = Path("artifacts/spot_controlled_exit/controlled_fill_exit_plan.json")
    accounting_path: Path = Path("artifacts/spot_controlled_exit/micro_position_accounting.json")
    policy_path: Path = Path("artifacts/spot_controlled_exit/manual_automated_exit_policy.json")
    pnl_reconciliation_path: Path = Path(
        "artifacts/spot_controlled_exit/fee_spread_pnl_reconciliation.json"
    )
    session_report_path: Path = Path("artifacts/spot_controlled_exit/controlled_fill_session_report.json")
    kill_switch_path: Path = Path(
        "artifacts/spot_controlled_exit/kill_switch_residual_inventory.json"
    )

class Phase35GateReport(BaseModel):
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


class ControlledFillExitPlanReport(Phase35GateReport):
    source: str = "spot_brl_controlled_non_market_fill_exit_plan"

    symbol: str
    policy: str
    position_detected: bool
    base_free: float
    quote_free: float
    open_orders_count: int
    current_price: float
    entry_executed_qty: float
    entry_cumulative_quote_qty: float
    entry_avg_price_brl: float
    estimated_position_value_brl: float
    estimated_gross_pnl_brl: float
    real_sell_allowed: bool


class MicroPositionAccountingReport(Phase35GateReport):
    source: str = "spot_brl_micro_position_accounting"

    symbol: str
    base_free: float
    base_locked: float
    quote_free: float
    quote_locked: float
    open_orders_count: int

    entry_executed_qty: float
    entry_cumulative_quote_qty: float
    entry_avg_price_brl: float
    estimated_fee_base_qty: float
    current_price: float
    current_position_value_brl: float
    estimated_gross_pnl_brl: float
    estimated_loss_brl: float


class ManualAutomatedExitPolicyReport(Phase35GateReport):
    source: str = "spot_brl_manual_automated_exit_policy"

    policy: str
    real_sell_allowed: bool
    manual_only: bool
    automated_exit_enabled: bool
    max_sell_base_qty: float
    min_expected_quote_brl: float
    max_acceptable_loss_brl: float

class FeeSpreadPnlReconciliationReport(Phase35GateReport):
    source: str = "spot_brl_fee_spread_pnl_reconciliation"

    symbol: str
    base_free: float
    quote_free: float
    open_orders_count: int

    entry_executed_qty: float
    entry_cumulative_quote_qty: float
    entry_avg_price_brl: float

    current_price: float
    estimated_exit_price_brl: float
    estimated_gross_exit_value_brl: float
    estimated_exit_fee_brl: float
    estimated_net_exit_value_brl: float
    estimated_net_pnl_brl: float
    estimated_loss_brl: float

    fee_rate: float
    spread_buffer_pct: float
    min_net_pnl_brl: float

class KillSwitchResidualInventoryReport(Phase35GateReport):
    source: str = "spot_brl_kill_switch_residual_inventory"

    symbol: str

    attempted: bool
    kill_switch_allowed: bool
    kill_switch_passed: bool

    base_free_before: float
    base_locked_before: float
    quote_free_before: float
    quote_locked_before: float
    open_orders_before: int

    base_free_after: float
    base_locked_after: float
    quote_free_after: float
    quote_locked_after: float
    open_orders_after: int

    residual_inventory_detected: bool
    inventory_preserved: bool
    real_sell_allowed: bool

class ControlledFillSessionReport(Phase35GateReport):
    source: str = "spot_brl_controlled_fill_session_report"

    plan_passed: bool
    accounting_passed: bool
    policy_passed: bool
    pnl_passed: bool
    kill_switch_passed: bool
    real_sell_allowed: bool
    position_detected: bool
    open_orders_count: int
    final_reconciled: bool


def load_phase35_config() -> ControlledExitConfig:
    return ControlledExitConfig(
        output_dir=Path(
            os.getenv("SPOT_CONTROLLED_EXIT_OUTPUT_DIR", "artifacts/spot_controlled_exit")
        ),
        symbol=os.getenv("SPOT_CONTROLLED_EXIT_SYMBOL", "BTCBRL"),
        base_asset=os.getenv("SPOT_CONTROLLED_EXIT_BASE_ASSET", "BTC"),
        quote_asset=os.getenv("SPOT_CONTROLLED_EXIT_QUOTE_ASSET", "BRL"),
        base_free_baseline=env_float("SPOT_CONTROLLED_EXIT_BASE_FREE_BASELINE", 0.00003996),
        quote_free_baseline=env_float("SPOT_CONTROLLED_EXIT_QUOTE_FREE_BASELINE", 17.00184),
        entry_executed_qty=env_float("SPOT_CONTROLLED_EXIT_ENTRY_EXECUTED_QTY", 0.00004000),
        entry_cumulative_quote_qty=env_float(
            "SPOT_CONTROLLED_EXIT_ENTRY_CUMULATIVE_QUOTE_QTY",
            12.99816000,
        ),
        policy=os.getenv("SPOT_CONTROLLED_EXIT_POLICY", "MANUAL_ONLY"),
        allow_real_sell=env_bool("SPOT_CONTROLLED_EXIT_ALLOW_REAL_SELL", False),
        allow_cancel=env_bool("SPOT_CONTROLLED_EXIT_ALLOW_CANCEL", False),
        confirmation_phrase=os.getenv("SPOT_CONTROLLED_EXIT_CONFIRM_PHRASE", ""),
        allow_kill_switch=env_bool("SPOT_CONTROLLED_EXIT_ALLOW_KILL_SWITCH", False),
        kill_switch_confirmation_phrase=os.getenv(
            "SPOT_CONTROLLED_EXIT_KILL_SWITCH_CONFIRM_PHRASE",
            "",
        ),
        fee_rate=env_float("SPOT_CONTROLLED_EXIT_FEE_RATE", 0.001),
        spread_buffer_pct=env_float("SPOT_CONTROLLED_EXIT_SPREAD_BUFFER_PCT", 0.002),
        min_net_pnl_brl=env_float("SPOT_CONTROLLED_EXIT_MIN_NET_PNL_BRL", 0.0),        plan_path=Path(
            os.getenv(
                "SPOT_CONTROLLED_EXIT_PLAN_PATH",
                "artifacts/spot_controlled_exit/controlled_fill_exit_plan.json",
            )
        ),
        accounting_path=Path(
            os.getenv(
                "SPOT_CONTROLLED_POSITION_ACCOUNTING_PATH",
                "artifacts/spot_controlled_exit/micro_position_accounting.json",
            )
        ),
        policy_path=Path(
            os.getenv(
                "SPOT_CONTROLLED_EXIT_POLICY_PATH",
                "artifacts/spot_controlled_exit/manual_automated_exit_policy.json",
            )
        ),
        pnl_reconciliation_path=Path(
            os.getenv(
                "SPOT_CONTROLLED_PNL_RECONCILIATION_PATH",
                "artifacts/spot_controlled_exit/fee_spread_pnl_reconciliation.json",
            )
        ),
        kill_switch_path=Path(
            os.getenv(
                "SPOT_CONTROLLED_KILL_SWITCH_PATH",
                "artifacts/spot_controlled_exit/kill_switch_residual_inventory.json",
            )
        ),
        session_report_path=Path(
            os.getenv(
                "SPOT_CONTROLLED_SESSION_REPORT_PATH",
                "artifacts/spot_controlled_exit/controlled_fill_session_report.json",
            )
        ),
    )


def locked_phase33b_config_for_phase35(config: ControlledExitConfig) -> SpotMicroLiveConfig:
    base = load_phase33b_config()
    data = base.model_dump()

    data.update(
        {
            "symbol": config.symbol,
            "base_asset": config.base_asset,
            "quote_asset": config.quote_asset,
            "allow_real_order_submission": False,
            "allow_real_cancel": False,
            "confirmation_phrase": "",
            "spot_trading_enabled_declared": False,
        }
    )

    return SpotMicroLiveConfig(**data)

def kill_switch_phase33b_config_for_phase35(
    config: ControlledExitConfig,
) -> SpotMicroLiveConfig:
    base = load_phase33b_config()
    data = base.model_dump()

    data.update(
        {
            "symbol": config.symbol,
            "base_asset": config.base_asset,
            "quote_asset": config.quote_asset,
            "allow_real_order_submission": False,
            "allow_real_cancel": bool(config.allow_kill_switch),
            "allow_kill_switch": bool(config.allow_kill_switch),
            "confirmation_phrase": "",
            "spot_trading_enabled_declared": False,
        }
    )

    return SpotMicroLiveConfig(**data)

def safe_entry_avg_price(config: ControlledExitConfig) -> float:
    if config.entry_executed_qty <= 0:
        return 0.0

    return config.entry_cumulative_quote_qty / config.entry_executed_qty


def run_controlled_fill_exit_plan(
    config: ControlledExitConfig | None = None,
) -> ControlledFillExitPlanReport:
    resolved = config or load_phase35_config()

    phase33b = locked_phase33b_config_for_phase35(resolved)
    readonly = run_spot_readonly_snapshot(phase33b)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    current_price = 0.0

    try:
        current_price = get_current_price(phase33b)
    except Exception as exc:
        warnings.append(f"current_price_lookup_failed: {exc}")

    if readonly.passed is not True:
        blockers.append("readonly_snapshot_not_passed")

    if resolved.require_open_orders_zero and readonly.open_orders_count != 0:
        blockers.append("open_orders_detected_before_exit_plan")

    if resolved.require_no_locked_balance and (
        readonly.base_locked > 0 or readonly.quote_locked > 0
    ):
        blockers.append("locked_balance_detected_before_exit_plan")

    position_detected = readonly.base_free > 0

    if not position_detected:
        blockers.append("no_base_inventory_detected_for_exit_plan")

    entry_avg = safe_entry_avg_price(resolved)
    estimated_value = readonly.base_free * current_price
    estimated_gross_pnl = estimated_value - resolved.entry_cumulative_quote_qty

    if resolved.policy != "MANUAL_ONLY":
        warnings.append("policy_not_manual_only_review_required")

    if resolved.allow_real_sell:
        blockers.append("real_sell_must_remain_disabled_for_plan")

    recommendations.append("Nesta etapa, não executar venda real.")
    recommendations.append("Plano deve apenas reconhecer posição, preço médio, valor estimado e risco.")
    recommendations.append("Saída automática só deve ser liberada em etapa posterior com frase de confirmação.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return ControlledFillExitPlanReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        policy=resolved.policy,
        position_detected=position_detected,
        base_free=readonly.base_free,
        quote_free=readonly.quote_free,
        open_orders_count=readonly.open_orders_count,
        current_price=current_price,
        entry_executed_qty=resolved.entry_executed_qty,
        entry_cumulative_quote_qty=resolved.entry_cumulative_quote_qty,
        entry_avg_price_brl=entry_avg,
        estimated_position_value_brl=estimated_value,
        estimated_gross_pnl_brl=estimated_gross_pnl,
        real_sell_allowed=resolved.allow_real_sell,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def build_micro_position_accounting(
    config: ControlledExitConfig | None = None,
) -> MicroPositionAccountingReport:
    resolved = config or load_phase35_config()

    phase33b = locked_phase33b_config_for_phase35(resolved)
    readonly = run_spot_readonly_snapshot(phase33b)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    current_price = 0.0

    try:
        current_price = get_current_price(phase33b)
    except Exception as exc:
        warnings.append(f"current_price_lookup_failed: {exc}")

    if readonly.passed is not True:
        blockers.append("readonly_snapshot_not_passed")

    if readonly.open_orders_count != 0:
        blockers.append("open_orders_detected")

    if readonly.base_locked > 0 or readonly.quote_locked > 0:
        blockers.append("locked_balance_detected")

    entry_avg = safe_entry_avg_price(resolved)
    estimated_fee_base_qty = max(resolved.entry_executed_qty - readonly.base_free, 0.0)
    current_position_value = readonly.base_free * current_price
    estimated_gross_pnl = current_position_value - resolved.entry_cumulative_quote_qty
    estimated_loss = max(-estimated_gross_pnl, 0.0)

    if estimated_loss > resolved.max_acceptable_loss_brl:
        warnings.append("estimated_loss_above_configured_threshold")

    recommendations.append("PnL é estimado; valor final depende de preço de saída, taxas e spread.")
    recommendations.append("Fee em BTC é estimada pela diferença entre executed_qty e base_free.")
    recommendations.append("Não tomar decisão automática de venda nesta etapa.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return MicroPositionAccountingReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        base_free=readonly.base_free,
        base_locked=readonly.base_locked,
        quote_free=readonly.quote_free,
        quote_locked=readonly.quote_locked,
        open_orders_count=readonly.open_orders_count,
        entry_executed_qty=resolved.entry_executed_qty,
        entry_cumulative_quote_qty=resolved.entry_cumulative_quote_qty,
        entry_avg_price_brl=entry_avg,
        estimated_fee_base_qty=estimated_fee_base_qty,
        current_price=current_price,
        current_position_value_brl=current_position_value,
        estimated_gross_pnl_brl=estimated_gross_pnl,
        estimated_loss_brl=estimated_loss,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def build_manual_automated_exit_policy(
    config: ControlledExitConfig | None = None,
) -> ManualAutomatedExitPolicyReport:
    resolved = config or load_phase35_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    manual_only = resolved.policy == "MANUAL_ONLY"
    automated_exit_enabled = resolved.policy == "AUTO_LIMIT_EXIT"

    if not manual_only:
        warnings.append("policy_is_not_manual_only")

    if resolved.allow_real_sell:
        blockers.append("real_sell_not_allowed_in_policy_review")

    if resolved.allow_cancel:
        blockers.append("real_cancel_not_allowed_in_policy_review")

    if resolved.confirmation_phrase:
        blockers.append("confirmation_phrase_must_be_empty_in_policy_review")

    recommendations.append("Política inicial deve ser MANUAL_ONLY.")
    recommendations.append("AUTO_LIMIT_EXIT só deve ser implementado após validação de accounting e PnL.")
    recommendations.append("Venda real deve exigir flag, frase exata e novo gate de reconciliação.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return ManualAutomatedExitPolicyReport(
        status=status,
        passed=passed,
        decision=decision,
        policy=resolved.policy,
        real_sell_allowed=resolved.allow_real_sell,
        manual_only=manual_only,
        automated_exit_enabled=automated_exit_enabled,
        max_sell_base_qty=resolved.max_sell_base_qty,
        min_expected_quote_brl=resolved.min_expected_quote_brl,
        max_acceptable_loss_brl=resolved.max_acceptable_loss_brl,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )

def build_fee_spread_pnl_reconciliation(
    config: ControlledExitConfig | None = None,
) -> FeeSpreadPnlReconciliationReport:
    resolved = config or load_phase35_config()

    phase33b = locked_phase33b_config_for_phase35(resolved)
    readonly = run_spot_readonly_snapshot(phase33b)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    current_price = 0.0

    try:
        current_price = get_current_price(phase33b)
    except Exception as exc:
        blockers.append("current_price_lookup_failed")
        warnings.append(str(exc))

    if readonly.passed is not True:
        blockers.append("readonly_snapshot_not_passed")

    if readonly.open_orders_count != 0:
        blockers.append("open_orders_detected")

    if readonly.base_locked > 0 or readonly.quote_locked > 0:
        blockers.append("locked_balance_detected")

    if readonly.base_free <= 0:
        blockers.append("no_base_inventory_detected")

    entry_avg = safe_entry_avg_price(resolved)

    estimated_exit_price = current_price * (1.0 - resolved.spread_buffer_pct)
    estimated_gross_exit_value = readonly.base_free * estimated_exit_price
    estimated_exit_fee = estimated_gross_exit_value * resolved.fee_rate
    estimated_net_exit_value = estimated_gross_exit_value - estimated_exit_fee
    estimated_net_pnl = estimated_net_exit_value - resolved.entry_cumulative_quote_qty
    estimated_loss = max(-estimated_net_pnl, 0.0)

    if estimated_loss > resolved.max_acceptable_loss_brl:
        warnings.append("estimated_loss_above_configured_threshold")

    if estimated_net_pnl < resolved.min_net_pnl_brl:
        warnings.append("estimated_net_pnl_below_configured_minimum")

    recommendations.append("Este relatório é apenas estimativo; não executa venda real.")
    recommendations.append("PnL líquido depende de preço de execução, taxa real e spread.")
    recommendations.append("Só avançar para exit dry-run se open_orders=0 e locked balances=0.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return FeeSpreadPnlReconciliationReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        base_free=readonly.base_free,
        quote_free=readonly.quote_free,
        open_orders_count=readonly.open_orders_count,
        entry_executed_qty=resolved.entry_executed_qty,
        entry_cumulative_quote_qty=resolved.entry_cumulative_quote_qty,
        entry_avg_price_brl=entry_avg,
        current_price=current_price,
        estimated_exit_price_brl=estimated_exit_price,
        estimated_gross_exit_value_brl=estimated_gross_exit_value,
        estimated_exit_fee_brl=estimated_exit_fee,
        estimated_net_exit_value_brl=estimated_net_exit_value,
        estimated_net_pnl_brl=estimated_net_pnl,
        estimated_loss_brl=estimated_loss,
        fee_rate=resolved.fee_rate,
        spread_buffer_pct=resolved.spread_buffer_pct,
        min_net_pnl_brl=resolved.min_net_pnl_brl,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )

def run_kill_switch_residual_inventory(
    config: ControlledExitConfig | None = None,
) -> KillSwitchResidualInventoryReport:
    resolved = config or load_phase35_config()

    readonly_config = locked_phase33b_config_for_phase35(resolved)
    before = run_spot_readonly_snapshot(readonly_config)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    attempted = False
    kill_switch_passed = False

    if before.passed is not True:
        blockers.append("readonly_before_kill_switch_not_passed")

    if resolved.allow_real_sell:
        blockers.append("real_sell_must_remain_disabled_for_kill_switch")

    residual_inventory_detected = before.base_free > 0

    if not residual_inventory_detected:
        warnings.append("no_residual_inventory_detected")

    if before.base_locked > 0 or before.quote_locked > 0:
        blockers.append("locked_balance_detected_before_kill_switch")

    if before.open_orders_count == 0:
        recommendations.append("Nenhuma ordem aberta encontrada; kill switch permanece como validação de segurança.")

    can_attempt = (
        resolved.allow_kill_switch
        and resolved.kill_switch_confirmation_phrase
        == "I_ACCEPT_SPOT_CONTROLLED_EXIT_KILL_SWITCH_RISK"
        and not blockers
    )

    if resolved.allow_kill_switch and not can_attempt:
        blockers.append("kill_switch_confirmation_phrase_required")

    after = before

    if can_attempt:
        attempted = True
        kill_config = kill_switch_phase33b_config_for_phase35(resolved)
        drill = run_spot_kill_switch(kill_config)

        kill_switch_passed = drill.passed

        if drill.passed is not True:
            blockers.append("kill_switch_not_passed")

        after = run_spot_readonly_snapshot(readonly_config)

        if after.passed is not True:
            blockers.append("readonly_after_kill_switch_not_passed")
    else:
        kill_switch_passed = before.passed and before.open_orders_count == 0

    inventory_preserved = abs(after.base_free - before.base_free) <= 0.00000001

    if not inventory_preserved:
        blockers.append("residual_inventory_changed_during_kill_switch")

    if after.open_orders_count != 0:
        blockers.append("open_orders_remaining_after_kill_switch")

    if after.base_locked > 0 or after.quote_locked > 0:
        blockers.append("locked_balance_detected_after_kill_switch")

    recommendations.append("Kill switch deve cancelar ordens abertas, não vender inventário BTC.")
    recommendations.append("Venda residual deve ficar para etapa de exit dry-run/controlled sell.")
    recommendations.append("Confirmar sempre open_orders=0 e locked balances=0 após o drill.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return KillSwitchResidualInventoryReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        attempted=attempted,
        kill_switch_allowed=resolved.allow_kill_switch,
        kill_switch_passed=kill_switch_passed,
        base_free_before=before.base_free,
        base_locked_before=before.base_locked,
        quote_free_before=before.quote_free,
        quote_locked_before=before.quote_locked,
        open_orders_before=before.open_orders_count,
        base_free_after=after.base_free,
        base_locked_after=after.base_locked,
        quote_free_after=after.quote_free,
        quote_locked_after=after.quote_locked,
        open_orders_after=after.open_orders_count,
        residual_inventory_detected=residual_inventory_detected,
        inventory_preserved=inventory_preserved,
        real_sell_allowed=resolved.allow_real_sell,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),

    )


def build_controlled_fill_session_report(
    config: ControlledExitConfig | None = None,
) -> ControlledFillSessionReport:
    resolved = config or load_phase35_config()

    plan = load_json(resolved.plan_path)
    accounting = load_json(resolved.accounting_path)
    policy = load_json(resolved.policy_path)
    pnl = load_json(resolved.pnl_reconciliation_path)
    kill_switch = load_json(resolved.kill_switch_path)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    plan_passed = plan.get("passed") is True if plan else False
    accounting_passed = accounting.get("passed") is True if accounting else False
    policy_passed = policy.get("passed") is True if policy else False
    pnl_passed = pnl.get("passed") is True if pnl else False
    kill_switch_passed = kill_switch.get("passed") is True if kill_switch else False
    real_sell_allowed = policy.get("real_sell_allowed") is True if policy else False
    position_detected = plan.get("position_detected") is True if plan else False
    open_orders_count = int(plan.get("open_orders_count", 999)) if plan else 999
    final_reconciled = open_orders_count == 0

    if not plan_passed:
        blockers.append("controlled_exit_plan_not_passed")

    if not accounting_passed:
        blockers.append("micro_position_accounting_not_passed")

    if not policy_passed:
        blockers.append("exit_policy_not_passed")

    if not pnl_passed:
        blockers.append("pnl_reconciliation_not_passed")

    if not kill_switch_passed:
        blockers.append("kill_switch_residual_inventory_not_passed")

    if real_sell_allowed:
        blockers.append("real_sell_unexpectedly_enabled")

    if open_orders_count != 0:
        blockers.append("open_orders_detected")

    if not position_detected:
        warnings.append("no_position_detected_session_may_be_complete_already")

    recommendations.append("Fase 35 inicial aprova somente plano, accounting e política manual.")
    recommendations.append("Próximo passo deve implementar exit dry-run antes de qualquer venda real.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return ControlledFillSessionReport(
        status=status,
        passed=passed,
        decision=decision,
        plan_passed=plan_passed,
        accounting_passed=accounting_passed,
        policy_passed=policy_passed,
        pnl_passed=pnl_passed,
        kill_switch_passed=kill_switch_passed,
        real_sell_allowed=real_sell_allowed,
        position_detected=position_detected,
        open_orders_count=open_orders_count,
        final_reconciled=final_reconciled,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )