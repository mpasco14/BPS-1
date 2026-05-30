from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()

__test__ = False


CampaignSessionStatus = Literal["PASS", "WARN", "FAIL", "BLOCKED"]
CampaignDecision = Literal[
    "FIX_REQUIRED",
    "REPEAT_TESTNET_CAMPAIGN",
    "APPROVED_FOR_REAL_TESTNET_CAMPAIGN",
    "APPROVED_FOR_MICRO_LIVE_PREP",
]


class LongTestnetCampaignConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_campaign")

    symbol: str = "BTCUSDT"
    side: Literal["BUY", "SELL"] = "BUY"
    quantity: float = 0.001
    price: float = 60000.0

    simulate: bool = True
    allow_real_submit: bool = False
    allow_real_cancel: bool = False
    require_no_live_flags: bool = True

    durations_minutes: list[int] = Field(default_factory=lambda: [30, 120, 360, 720])

    require_30min_pass: bool = True
    require_2h_pass: bool = True
    require_6h_pass: bool = True
    require_12h_pass: bool = True

    require_final_flat: bool = True
    require_test_order_pass: bool = True
    require_no_rejections: bool = True
    require_no_blockers: bool = True


class CampaignSessionPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_name: str
    duration_minutes: int
    symbol: str = "BTCUSDT"
    side: Literal["BUY", "SELL"] = "BUY"
    quantity: float = 0.001
    price: float = 60000.0

    simulate: bool = True
    allow_real_submit: bool = False
    allow_real_cancel: bool = False

    planned_checks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignSessionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "long_real_testnet_campaign_session"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: CampaignSessionStatus
    passed: bool
    simulated: bool

    session_name: str
    duration_minutes: int
    symbol: str

    test_order_passed: bool = False
    submit_passed: bool = False
    submitted: bool = False
    cancel_attempted: bool = False
    cancel_passed: bool = False
    fill_detected: bool = False
    rejection_detected: bool = False
    final_flat: bool = False

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    plan: dict[str, Any]
    lifecycle_report: dict[str, Any]


class MultiSessionCampaignReview(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "multi_session_testnet_campaign_review"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: CampaignSessionStatus
    passed: bool
    decision: CampaignDecision

    simulated: bool
    sessions_count: int
    passed_sessions_count: int
    failed_sessions_count: int

    required_durations_minutes: list[int] = Field(default_factory=list)
    completed_durations_minutes: list[int] = Field(default_factory=list)

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    sessions: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int_list(name: str, default: list[int]) -> list[int]:
    value = os.getenv(name)

    if not value:
        return default

    result: list[int] = []

    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError:
            continue

    return result or default


def live_flags_detected() -> bool:
    return any(
        [
            env_bool("BINANCE_ALLOW_LIVE_TRADING", False),
            env_bool("RISK_ALLOW_LIVE_TRADING", False),
            env_bool("LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION", False),
        ]
    )


def load_long_testnet_campaign_config() -> LongTestnetCampaignConfig:
    return LongTestnetCampaignConfig(
        output_dir=Path(os.getenv("TESTNET_CAMPAIGN_OUTPUT_DIR", "artifacts/testnet_campaign")),
        symbol=os.getenv("TESTNET_CAMPAIGN_SYMBOL", "BTCUSDT"),
        side=os.getenv("TESTNET_CAMPAIGN_SIDE", "BUY"),
        quantity=env_float("TESTNET_CAMPAIGN_QUANTITY", 0.001),
        price=env_float("TESTNET_CAMPAIGN_PRICE", 60000),
        simulate=env_bool("TESTNET_CAMPAIGN_SIMULATE", True),
        allow_real_submit=env_bool("TESTNET_CAMPAIGN_ALLOW_REAL_SUBMIT", False),
        allow_real_cancel=env_bool("TESTNET_CAMPAIGN_ALLOW_REAL_CANCEL", False),
        require_no_live_flags=env_bool("TESTNET_CAMPAIGN_REQUIRE_NO_LIVE_FLAGS", True),
        durations_minutes=env_int_list("TESTNET_CAMPAIGN_DURATIONS_MINUTES", [30, 120, 360, 720]),
        require_30min_pass=env_bool("TESTNET_CAMPAIGN_REQUIRE_30MIN_PASS", True),
        require_2h_pass=env_bool("TESTNET_CAMPAIGN_REQUIRE_2H_PASS", True),
        require_6h_pass=env_bool("TESTNET_CAMPAIGN_REQUIRE_6H_PASS", True),
        require_12h_pass=env_bool("TESTNET_CAMPAIGN_REQUIRE_12H_PASS", True),
        require_final_flat=env_bool("TESTNET_CAMPAIGN_REQUIRE_FINAL_FLAT", True),
        require_test_order_pass=env_bool("TESTNET_CAMPAIGN_REQUIRE_TEST_ORDER_PASS", True),
        require_no_rejections=env_bool("TESTNET_CAMPAIGN_REQUIRE_NO_REJECTIONS", True),
        require_no_blockers=env_bool("TESTNET_CAMPAIGN_REQUIRE_NO_BLOCKERS", True),
    )


def export_campaign_json(
    payload: BaseModel | dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    name: str,
) -> Path:
    config = load_long_testnet_campaign_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path