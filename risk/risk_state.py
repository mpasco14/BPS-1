from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


RiskStateStatus = Literal["OK", "WARN", "BLOCKED"]


class RiskStateConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/risk")
    state_file: Path = Path("artifacts/risk/risk_state_latest.json")

    max_daily_loss_usd: float = 5.0
    max_open_positions: int = 1
    max_open_orders: int = 3
    max_total_exposure_usd: float = 600.0
    max_btc_directional_exposure_usd: float = 600.0


class OpenOrderSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    side: str
    quantity: float
    price: float | None = None
    notional_usd: float = 0.0
    status: str = "NEW"
    order_id: str | int | None = None
    client_order_id: str | None = None
    timeframe: str | None = None


class OpenPositionSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    side: str
    quantity: float
    entry_price: float
    notional_usd: float
    margin_usd: float
    leverage: int
    unrealized_pnl_usd: float = 0.0
    timeframe: str | None = None


class RiskStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "risk_state"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    total_balance_usd: float = 0.0
    daily_realized_pnl_usd: float = 0.0
    daily_unrealized_pnl_usd: float = 0.0

    open_orders: list[dict[str, Any]] = Field(default_factory=list)
    open_positions: list[dict[str, Any]] = Field(default_factory=list)

    total_open_orders: int = 0
    total_open_positions: int = 0

    total_exposure_usd: float = 0.0
    btc_directional_exposure_usd: float = 0.0

    exposure_by_symbol: dict[str, float] = Field(default_factory=dict)
    exposure_by_timeframe: dict[str, float] = Field(default_factory=dict)

    status: RiskStateStatus = "OK"
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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


def load_risk_state_config() -> RiskStateConfig:
    return RiskStateConfig(
        output_dir=Path(os.getenv("RISK_STATE_OUTPUT_DIR", "artifacts/risk")),
        state_file=Path(os.getenv("RISK_STATE_FILE", "artifacts/risk/risk_state_latest.json")),
        max_daily_loss_usd=env_float("RISK_STATE_MAX_DAILY_LOSS_USD", 5),
        max_open_positions=env_int("RISK_STATE_MAX_OPEN_POSITIONS", 1),
        max_open_orders=env_int("RISK_STATE_MAX_OPEN_ORDERS", 3),
        max_total_exposure_usd=env_float("RISK_STATE_MAX_TOTAL_EXPOSURE_USD", 600),
        max_btc_directional_exposure_usd=env_float("RISK_STATE_MAX_BTC_DIRECTIONAL_EXPOSURE_USD", 600),
    )


def build_risk_state_snapshot(
    *,
    open_orders: list[OpenOrderSnapshot | dict[str, Any]] | None = None,
    open_positions: list[OpenPositionSnapshot | dict[str, Any]] | None = None,
    daily_realized_pnl_usd: float = 0.0,
    daily_unrealized_pnl_usd: float = 0.0,
    total_balance_usd: float = 0.0,
    config: RiskStateConfig | None = None,
) -> RiskStateSnapshot:
    resolved_config = config or load_risk_state_config()

    parsed_orders = [
        item if isinstance(item, OpenOrderSnapshot) else OpenOrderSnapshot.model_validate(item)
        for item in (open_orders or [])
    ]
    parsed_positions = [
        item if isinstance(item, OpenPositionSnapshot) else OpenPositionSnapshot.model_validate(item)
        for item in (open_positions or [])
    ]

    exposure_by_symbol: dict[str, float] = {}
    exposure_by_timeframe: dict[str, float] = {}

    total_exposure = 0.0
    btc_directional_exposure = 0.0

    for position in parsed_positions:
        exposure = abs(float(position.notional_usd))
        total_exposure += exposure

        exposure_by_symbol[position.symbol] = exposure_by_symbol.get(position.symbol, 0.0) + exposure

        if position.timeframe:
            exposure_by_timeframe[position.timeframe] = exposure_by_timeframe.get(position.timeframe, 0.0) + exposure

        if position.symbol.upper() == "BTCUSDT":
            if position.side.upper() == "LONG":
                btc_directional_exposure += exposure
            elif position.side.upper() == "SHORT":
                btc_directional_exposure -= exposure

    blockers: list[str] = []
    warnings: list[str] = []

    if daily_realized_pnl_usd <= -abs(resolved_config.max_daily_loss_usd):
        blockers.append("daily_loss_limit_reached")

    if len(parsed_positions) > resolved_config.max_open_positions:
        blockers.append("max_open_positions_exceeded")

    if len(parsed_orders) > resolved_config.max_open_orders:
        blockers.append("max_open_orders_exceeded")

    if total_exposure > resolved_config.max_total_exposure_usd:
        blockers.append("total_exposure_above_limit")

    if abs(btc_directional_exposure) > resolved_config.max_btc_directional_exposure_usd:
        blockers.append("btc_directional_exposure_above_limit")

    if daily_unrealized_pnl_usd < 0:
        warnings.append("unrealized_pnl_negative")

    status: RiskStateStatus = "BLOCKED" if blockers else ("WARN" if warnings else "OK")

    return RiskStateSnapshot(
        total_balance_usd=total_balance_usd,
        daily_realized_pnl_usd=daily_realized_pnl_usd,
        daily_unrealized_pnl_usd=daily_unrealized_pnl_usd,
        open_orders=[item.model_dump(mode="json") for item in parsed_orders],
        open_positions=[item.model_dump(mode="json") for item in parsed_positions],
        total_open_orders=len(parsed_orders),
        total_open_positions=len(parsed_positions),
        total_exposure_usd=total_exposure,
        btc_directional_exposure_usd=btc_directional_exposure,
        exposure_by_symbol=exposure_by_symbol,
        exposure_by_timeframe=exposure_by_timeframe,
        status=status,
        blockers=blockers,
        warnings=warnings,
    )


def export_risk_state_snapshot(
    snapshot: RiskStateSnapshot,
    *,
    path: str | Path | None = None,
) -> Path:
    config = load_risk_state_config()
    output_path = Path(path or config.state_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def load_risk_state_snapshot(path: str | Path | None = None) -> RiskStateSnapshot | None:
    config = load_risk_state_config()
    input_path = Path(path or config.state_file)

    if not input_path.exists():
        return None

    return RiskStateSnapshot.model_validate(
        json.loads(input_path.read_text(encoding="utf-8"))
    )