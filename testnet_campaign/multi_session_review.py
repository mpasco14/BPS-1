from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from testnet_campaign.campaign_models import (
    CampaignDecision,
    CampaignSessionResult,
    LongTestnetCampaignConfig,
    MultiSessionCampaignReview,
    export_campaign_json,
    load_long_testnet_campaign_config,
)


def required_durations_from_config(config: LongTestnetCampaignConfig) -> list[int]:
    required: list[int] = []

    if config.require_30min_pass:
        required.append(30)

    if config.require_2h_pass:
        required.append(120)

    if config.require_6h_pass:
        required.append(360)

    if config.require_12h_pass:
        required.append(720)

    return required


def review_multi_session_campaign(
    *,
    sessions: list[CampaignSessionResult | dict[str, Any]],
    config: LongTestnetCampaignConfig | None = None,
) -> MultiSessionCampaignReview:
    resolved = config or load_long_testnet_campaign_config()

    parsed_sessions = [
        item
        if isinstance(item, CampaignSessionResult)
        else CampaignSessionResult.model_validate(item)
        for item in sessions
    ]

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    required_durations = required_durations_from_config(resolved)
    completed_durations = sorted({item.duration_minutes for item in parsed_sessions if item.passed})

    sessions_by_duration = {item.duration_minutes: item for item in parsed_sessions}

    for duration in required_durations:
        session = sessions_by_duration.get(duration)

        if session is None:
            blockers.append(f"required_session_missing_{duration}min")
            continue

        if not session.passed:
            blockers.append(f"required_session_not_passed_{duration}min")
            blockers.extend([f"{duration}min:{item}" for item in session.blockers])

        if resolved.require_final_flat and not session.final_flat:
            blockers.append(f"{duration}min:final_position_not_flat")

        if resolved.require_test_order_pass and not session.test_order_passed:
            blockers.append(f"{duration}min:test_order_not_passed")

        if resolved.require_no_rejections and session.rejection_detected:
            blockers.append(f"{duration}min:rejection_detected")

    for session in parsed_sessions:
        warnings.extend([f"{session.duration_minutes}min:{item}" for item in session.warnings])

    simulated = any(item.simulated for item in parsed_sessions)

    passed_sessions_count = sum(1 for item in parsed_sessions if item.passed)
    failed_sessions_count = sum(1 for item in parsed_sessions if not item.passed)

    if failed_sessions_count:
        recommendations.append("Corrigir sessões com FAIL antes de avançar duração.")

    if simulated:
        warnings.append("campaign_contains_simulated_sessions")
        recommendations.append("Campanha simulada não autoriza micro-live; próxima etapa é campanha real testnet.")

    if blockers:
        decision: CampaignDecision = "FIX_REQUIRED"
    elif simulated:
        decision = "APPROVED_FOR_REAL_TESTNET_CAMPAIGN"
    else:
        decision = "APPROVED_FOR_MICRO_LIVE_PREP"

    if decision == "APPROVED_FOR_REAL_TESTNET_CAMPAIGN":
        recommendations.append("Rodar sequência real testnet: 30min → 2h → 6h → 12h.")

    if decision == "APPROVED_FOR_MICRO_LIVE_PREP":
        recommendations.append("Abrir Micro-Live Preparation Gate com aprovação humana e capital mínimo.")

    passed = not blockers

    return MultiSessionCampaignReview(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        decision=decision,
        simulated=simulated,
        sessions_count=len(parsed_sessions),
        passed_sessions_count=passed_sessions_count,
        failed_sessions_count=failed_sessions_count,
        required_durations_minutes=required_durations,
        completed_durations_minutes=completed_durations,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        sessions=[item.model_dump(mode="json") for item in parsed_sessions],
        config=resolved.model_dump(mode="json"),
    )


def export_multi_session_campaign_review(
    review: MultiSessionCampaignReview,
    *,
    output_dir: str | Path | None = None,
    name: str = "multi_session_testnet_campaign_review",
) -> Path:
    return export_campaign_json(
        review,
        output_dir=output_dir or os.getenv("TESTNET_CAMPAIGN_REVIEW_OUTPUT_DIR", "artifacts/testnet_campaign"),
        name=name,
    )