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


MicroLiveSessionStatus = Literal["PASS", "WARN", "FAIL", "BLOCKED"]
MicroLiveSessionDecision = Literal[
    "BLOCKED",
    "DRY_RUN_ONLY",
    "APPROVED_FOR_ONE_MICRO_LIVE_ORDER",
    "REPEAT_PREP_GATE",
    "FIX_REQUIRED",
]


class MicroLiveSessionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/micro_live_session")

    session_name: str = "first_micro_live_supervised"
    symbol: str = "BTCUSDT"
    side: Literal["BUY", "SELL"] = "BUY"
    quantity: float = 0.001
    price: float = 60000.0

    max_notional_usd: float = 10.0
    max_capital_usd: float = 25.0
    max_daily_loss_usd: float = 3.0
    max_leverage: int = 3

    dry_run: bool = True
    allow_live_order: bool = False

    require_prep_gate: bool = True
    require_human_approval: bool = True
    require_kill_switch: bool = True
    require_final_flat: bool = True
    require_no_rejection: bool = True
    require_read_only_pass: bool = True

    min_confidence: float = 0.70
    min_edge_pct: float = 0.001
    allow_no_trade: bool = False

    emergency_stop_file: Path = Path("artifacts/micro_live_session/emergency_stop.flag")


class MicroLiveSessionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_live_supervised_session_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: MicroLiveSessionStatus
    passed: bool
    decision: MicroLiveSessionDecision

    session_name: str
    dry_run: bool
    live_order_allowed: bool

    read_only_passed: bool = False
    dry_run_signal_passed: bool = False
    order_gate_passed: bool = False
    fill_reconciliation_passed: bool = False
    kill_switch_passed: bool = False

    submitted: bool = False
    filled: bool = False
    canceled: bool = False
    final_flat: bool = False

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    read_only_check: dict[str, Any] | None = None
    dry_run_signal: dict[str, Any] | None = None
    small_order: dict[str, Any] | None = None
    fill_reconciliation: dict[str, Any] | None = None
    kill_switch: dict[str, Any] | None = None

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


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_micro_live_session_config() -> MicroLiveSessionConfig:
    return MicroLiveSessionConfig(
        output_dir=Path(os.getenv("MICRO_LIVE_SESSION_OUTPUT_DIR", "artifacts/micro_live_session")),
        session_name=os.getenv("MICRO_LIVE_SESSION_NAME", "first_micro_live_supervised"),
        symbol=os.getenv("MICRO_LIVE_SESSION_SYMBOL", "BTCUSDT"),
        side=os.getenv("MICRO_LIVE_SESSION_SIDE", "BUY"),
        quantity=env_float("MICRO_LIVE_SESSION_QUANTITY", 0.001),
        price=env_float("MICRO_LIVE_SESSION_PRICE", 60000),
        max_notional_usd=env_float("MICRO_LIVE_SESSION_MAX_NOTIONAL_USD", 10),
        max_capital_usd=env_float("MICRO_LIVE_SESSION_MAX_CAPITAL_USD", 25),
        max_daily_loss_usd=env_float("MICRO_LIVE_SESSION_MAX_DAILY_LOSS_USD", 3),
        max_leverage=env_int("MICRO_LIVE_SESSION_MAX_LEVERAGE", 3),
        dry_run=env_bool("MICRO_LIVE_SESSION_DRY_RUN", True),
        allow_live_order=env_bool("MICRO_LIVE_SESSION_ALLOW_LIVE_ORDER", False),
        require_prep_gate=env_bool("MICRO_LIVE_SESSION_REQUIRE_PREP_GATE", True),
        require_human_approval=env_bool("MICRO_LIVE_SESSION_REQUIRE_HUMAN_APPROVAL", True),
        require_kill_switch=env_bool("MICRO_LIVE_SESSION_REQUIRE_KILL_SWITCH", True),
        require_final_flat=env_bool("MICRO_LIVE_SESSION_REQUIRE_FINAL_FLAT", True),
        require_no_rejection=env_bool("MICRO_LIVE_SESSION_REQUIRE_NO_REJECTION", True),
        require_read_only_pass=env_bool("MICRO_LIVE_SESSION_REQUIRE_READ_ONLY_PASS", True),
        min_confidence=env_float("MICRO_LIVE_SESSION_MIN_CONFIDENCE", 0.70),
        min_edge_pct=env_float("MICRO_LIVE_SESSION_MIN_EDGE_PCT", 0.001),
        allow_no_trade=env_bool("MICRO_LIVE_SESSION_ALLOW_NO_TRADE", False),
        emergency_stop_file=Path(
            os.getenv(
                "MICRO_LIVE_SESSION_EMERGENCY_STOP_FILE",
                "artifacts/micro_live_session/emergency_stop.flag",
            )
        ),
    )


def export_micro_live_session_json(
    payload: BaseModel | dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    name: str,
) -> Path:
    config = load_micro_live_session_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path