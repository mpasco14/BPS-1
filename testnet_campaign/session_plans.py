from __future__ import annotations

from testnet_campaign.campaign_models import (
    CampaignSessionPlan,
    LongTestnetCampaignConfig,
    load_long_testnet_campaign_config,
)


def session_label(duration_minutes: int) -> str:
    if duration_minutes == 30:
        return "30min"

    if duration_minutes == 120:
        return "2h"

    if duration_minutes == 360:
        return "6h"

    if duration_minutes == 720:
        return "12h"

    return f"{duration_minutes}min"


def build_campaign_session_plan(
    *,
    duration_minutes: int,
    session_name: str | None = None,
    config: LongTestnetCampaignConfig | None = None,
) -> CampaignSessionPlan:
    resolved = config or load_long_testnet_campaign_config()
    label = session_label(duration_minutes)

    return CampaignSessionPlan(
        session_name=session_name or f"real_testnet_campaign_{label}",
        duration_minutes=duration_minutes,
        symbol=resolved.symbol,
        side=resolved.side,
        quantity=resolved.quantity,
        price=resolved.price,
        simulate=resolved.simulate,
        allow_real_submit=resolved.allow_real_submit,
        allow_real_cancel=resolved.allow_real_cancel,
        planned_checks=[
            "credential_check",
            "test_order_validation",
            "small_limit_order_submit",
            "open_order_query",
            "cancel_or_fill_confirmation",
            "fill_rejection_capture",
            "position_reconciliation",
            "final_flat_validation",
            "session_artifact_export",
        ],
        metadata={
            "label": label,
            "progression_rule": "Do not advance to next duration unless this session passes.",
        },
    )


def build_default_campaign_session_plans(
    *,
    config: LongTestnetCampaignConfig | None = None,
) -> list[CampaignSessionPlan]:
    resolved = config or load_long_testnet_campaign_config()

    return [
        build_campaign_session_plan(
            duration_minutes=duration,
            config=resolved,
        )
        for duration in resolved.durations_minutes
    ]