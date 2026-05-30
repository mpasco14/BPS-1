from __future__ import annotations

import os
from pathlib import Path

from testnet_campaign.campaign_models import (
    CampaignSessionPlan,
    CampaignSessionResult,
    LongTestnetCampaignConfig,
    export_campaign_json,
    live_flags_detected,
    load_long_testnet_campaign_config,
)
from testnet_campaign.session_plans import build_default_campaign_session_plans
from testnet_order_lifecycle.lifecycle_models import TestnetOrderLifecycleConfig
from testnet_order_lifecycle.lifecycle_report import build_real_testnet_lifecycle_report


def build_lifecycle_config_for_campaign_session(
    *,
    plan: CampaignSessionPlan,
    config: LongTestnetCampaignConfig | None = None,
) -> TestnetOrderLifecycleConfig:
    resolved = config or load_long_testnet_campaign_config()

    return TestnetOrderLifecycleConfig(
        symbol=plan.symbol,
        side=plan.side,
        quantity=plan.quantity,
        price=plan.price,
        simulate=plan.simulate,
        allow_real_submit=plan.allow_real_submit,
        allow_real_cancel=True if plan.simulate else plan.allow_real_cancel,
        require_test_order_pass=True,
        require_cancel_attempt=True,
        require_final_flat=True,
        require_no_live_flags=resolved.require_no_live_flags,
        max_notional_usd=100.0,
        max_qty=max(0.001, plan.quantity),
        max_rejection_count=0,
        max_slippage_pct=0.005,
    )


def run_campaign_session(
    *,
    plan: CampaignSessionPlan,
    config: LongTestnetCampaignConfig | None = None,
) -> CampaignSessionResult:
    resolved = config or load_long_testnet_campaign_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved.require_no_live_flags and live_flags_detected():
        blockers.append("live_flags_detected")

    if plan.duration_minutes <= 0:
        blockers.append("duration_minutes_must_be_positive")

    if plan.quantity <= 0:
        blockers.append("quantity_must_be_positive")

    if plan.price <= 0:
        blockers.append("price_must_be_positive")

    if blockers:
        return CampaignSessionResult(
            status="BLOCKED",
            passed=False,
            simulated=plan.simulate,
            session_name=plan.session_name,
            duration_minutes=plan.duration_minutes,
            symbol=plan.symbol,
            blockers=blockers,
            warnings=warnings,
            recommendations=[
                "Corrigir configuração antes de rodar campanha testnet.",
                "Manter live flags desligadas.",
            ],
            plan=plan.model_dump(mode="json"),
            lifecycle_report={},
        )

    lifecycle_config = build_lifecycle_config_for_campaign_session(
        plan=plan,
        config=resolved,
    )
    lifecycle = build_real_testnet_lifecycle_report(config=lifecycle_config)

    if resolved.require_no_blockers and lifecycle.blockers:
        blockers.append("lifecycle_blockers_detected")
        blockers.extend([f"lifecycle:{item}" for item in lifecycle.blockers])

    if resolved.require_test_order_pass and not lifecycle.test_order_passed:
        blockers.append("test_order_not_passed")

    if resolved.require_no_rejections and lifecycle.rejection_detected:
        blockers.append("rejection_detected")

    if resolved.require_final_flat and not lifecycle.final_flat:
        blockers.append("final_position_not_flat")

    warnings.extend([f"lifecycle:{item}" for item in lifecycle.warnings])

    if plan.simulate:
        warnings.append("campaign_session_simulated")
        recommendations.append("Sessão simulada valida estrutura; para promoção real, rodar com testnet real.")

    recommendations.append("Só avançar para próxima duração se esta sessão passar sem blockers.")
    recommendations.append("Manter position final flat e artifacts completos.")

    passed = not blockers

    return CampaignSessionResult(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        simulated=plan.simulate,
        session_name=plan.session_name,
        duration_minutes=plan.duration_minutes,
        symbol=plan.symbol,
        test_order_passed=lifecycle.test_order_passed,
        submit_passed=lifecycle.submit_passed,
        submitted=lifecycle.submitted,
        cancel_attempted=lifecycle.cancel_attempted,
        cancel_passed=lifecycle.cancel_passed,
        fill_detected=lifecycle.fill_detected,
        rejection_detected=lifecycle.rejection_detected,
        final_flat=lifecycle.final_flat,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        plan=plan.model_dump(mode="json"),
        lifecycle_report=lifecycle.model_dump(mode="json"),
    )


def run_campaign_sessions(
    *,
    plans: list[CampaignSessionPlan] | None = None,
    config: LongTestnetCampaignConfig | None = None,
    stop_on_failure: bool = True,
) -> list[CampaignSessionResult]:
    resolved = config or load_long_testnet_campaign_config()
    resolved_plans = plans or build_default_campaign_session_plans(config=resolved)

    results: list[CampaignSessionResult] = []

    for plan in resolved_plans:
        result = run_campaign_session(plan=plan, config=resolved)
        results.append(result)

        if stop_on_failure and not result.passed:
            break

    return results


def export_campaign_session_result(
    result: CampaignSessionResult,
    *,
    output_dir: str | Path | None = None,
    name: str | None = None,
) -> Path:
    safe_name = name or result.session_name

    return export_campaign_json(
        result,
        output_dir=output_dir or os.getenv("TESTNET_CAMPAIGN_SESSION_OUTPUT_DIR", "artifacts/testnet_campaign"),
        name=safe_name,
    )