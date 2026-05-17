"""
Binance Futures risk manager.

Responsabilidades:
- Receber sinais do signal_engine.
- Aprovar ou bloquear uma ordem candidata.
- Calcular quantity, TP, SL, notional e risco.
- Aplicar limites antes do paper_executor ou executor real.

Este módulo NÃO executa ordens.
Este módulo NÃO acessa API da Binance.
Este módulo NÃO substitui compliance_check.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

from strategy.signal_engine import TradingSignal


load_dotenv()


RiskDecision = Literal["APPROVED", "BLOCKED"]
Direction = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class AccountRiskState:
    daily_pnl_usd: float = 0.0
    consecutive_losses: int = 0
    open_positions: int = 0
    open_orders: int = 0
    kill_switch_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RiskProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"

    margin_usd: float
    leverage: float
    notional_usd: float

    gross_take_profit_usd: float
    gross_stop_loss_usd: float

    estimated_entry_fee_usd: float = 0.0
    estimated_exit_fee_usd: float = 0.0

    max_leverage: float
    max_margin_usd: float
    max_notional_usd: float
    max_daily_loss_usd: float
    max_trade_loss_usd: float
    max_consecutive_losses: int
    max_open_positions: int
    max_open_orders: int

    max_spread_pct: float
    min_liquidity_usd: float
    min_confidence: float

    allow_live_trading: bool = False
    allow_paper_trading: bool = True

    @field_validator(
        "margin_usd",
        "leverage",
        "notional_usd",
        "gross_take_profit_usd",
        "gross_stop_loss_usd",
        "max_leverage",
        "max_margin_usd",
        "max_notional_usd",
    )
    @classmethod
    def positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("valor precisa ser maior que zero")
        return float(value)

    @field_validator("min_confidence")
    @classmethod
    def confidence_range(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("min_confidence deve estar entre 0 e 1")
        return float(value)


class OrderRiskPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str

    direction: Direction
    order_side: Literal["BUY", "SELL"]

    entry_price: float
    quantity: float
    notional_usd: float
    margin_usd: float
    leverage: float

    tp_move_pct: float
    sl_move_pct: float

    take_profit_price: float
    stop_loss_price: float

    gross_take_profit_usd: float
    gross_stop_loss_usd: float

    estimated_fees_usd: float
    expected_net_profit_usd: float
    max_loss_with_fees_usd: float

    risk_reward_ratio: float

    @field_validator("entry_price", "quantity", "notional_usd", "margin_usd", "leverage")
    @classmethod
    def positive_values(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("valor precisa ser maior que zero")
        return float(value)


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "risk_manager"
    decision: RiskDecision

    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str

    direction: str
    confidence: float

    blockers: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    order_plan: OrderRiskPlan | None = None

    account_state: dict[str, Any] = Field(default_factory=dict)
    signal: dict[str, Any] = Field(default_factory=dict)

    assessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def env_float(name: str, default: float) -> float:
    value = safe_float(os.getenv(name))
    if value is None:
        return default
    return value


def env_int(name: str, default: int) -> int:
    value = safe_float(os.getenv(name))
    if value is None:
        return default
    return int(value)


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_default_risk_profile() -> RiskProfile:
    margin_usd = env_float("RISK_MARGIN_USD", env_float("BINANCE_FUTURES_PAPER_MARGIN_USD", 20.0))
    leverage = env_float("RISK_LEVERAGE", env_float("BINANCE_FUTURES_PAPER_LEVERAGE", 30.0))
    notional_usd = env_float("RISK_NOTIONAL_USD", margin_usd * leverage)

    return RiskProfile(
        venue=os.getenv("RISK_PRIMARY_VENUE", "binance_futures"),
        symbol=os.getenv("RISK_SYMBOL", "BTCUSDT"),
        margin_usd=margin_usd,
        leverage=leverage,
        notional_usd=notional_usd,
        gross_take_profit_usd=env_float("RISK_GROSS_TAKE_PROFIT_USD", 2.10),
        gross_stop_loss_usd=env_float("RISK_GROSS_STOP_LOSS_USD", 1.05),
        estimated_entry_fee_usd=env_float("RISK_ESTIMATED_ENTRY_FEE_USD", 0.05),
        estimated_exit_fee_usd=env_float("RISK_ESTIMATED_EXIT_FEE_USD", 0.05),
        max_leverage=env_float("RISK_MAX_LEVERAGE", 30.0),
        max_margin_usd=env_float("RISK_MAX_MARGIN_USD", 20.0),
        max_notional_usd=env_float("RISK_MAX_NOTIONAL_USD", 600.0),
        max_daily_loss_usd=env_float("RISK_MAX_DAILY_LOSS_USD", 5.0),
        max_trade_loss_usd=env_float("RISK_MAX_TRADE_LOSS_USD", 1.05),
        max_consecutive_losses=env_int("RISK_MAX_CONSECUTIVE_LOSSES", 3),
        max_open_positions=env_int("RISK_MAX_OPEN_POSITIONS", 1),
        max_open_orders=env_int("RISK_MAX_OPEN_ORDERS", 3),
        max_spread_pct=env_float("RISK_MAX_SPREAD_PCT", 0.002),
        min_liquidity_usd=env_float("RISK_MIN_LIQUIDITY_USD", 50000.0),
        min_confidence=env_float("RISK_MIN_CONFIDENCE", 0.65),
        allow_live_trading=parse_bool(os.getenv("RISK_ALLOW_LIVE_TRADING"), default=False),
        allow_paper_trading=parse_bool(os.getenv("RISK_ALLOW_PAPER_TRADING"), default=True),
    )


def extract_market_quality(signal: TradingSignal) -> tuple[float | None, float | None]:
    raw = signal.raw_features or {}

    spread = safe_float(raw.get("binance_spread_pct"))
    liquidity = safe_float(raw.get("binance_liquidity_usd"))

    return spread, liquidity


def calculate_order_plan(
    *,
    direction: Direction,
    entry_price: float,
    timeframe: str,
    profile: RiskProfile,
) -> OrderRiskPlan:
    if entry_price <= 0:
        raise ValueError("entry_price precisa ser maior que zero")

    quantity = profile.notional_usd / entry_price

    tp_move_pct = profile.gross_take_profit_usd / profile.notional_usd
    sl_move_pct = profile.gross_stop_loss_usd / profile.notional_usd

    if direction == "LONG":
        take_profit_price = entry_price * (1 + tp_move_pct)
        stop_loss_price = entry_price * (1 - sl_move_pct)
        order_side = "BUY"
    else:
        take_profit_price = entry_price * (1 - tp_move_pct)
        stop_loss_price = entry_price * (1 + sl_move_pct)
        order_side = "SELL"

    estimated_fees = profile.estimated_entry_fee_usd + profile.estimated_exit_fee_usd
    expected_net_profit = profile.gross_take_profit_usd - estimated_fees
    max_loss_with_fees = profile.gross_stop_loss_usd + estimated_fees

    risk_reward_ratio = profile.gross_take_profit_usd / profile.gross_stop_loss_usd

    return OrderRiskPlan(
        venue=profile.venue,
        symbol=profile.symbol,
        timeframe=timeframe,
        direction=direction,
        order_side=order_side,
        entry_price=entry_price,
        quantity=quantity,
        notional_usd=profile.notional_usd,
        margin_usd=profile.margin_usd,
        leverage=profile.leverage,
        tp_move_pct=tp_move_pct,
        sl_move_pct=sl_move_pct,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
        gross_take_profit_usd=profile.gross_take_profit_usd,
        gross_stop_loss_usd=profile.gross_stop_loss_usd,
        estimated_fees_usd=estimated_fees,
        expected_net_profit_usd=expected_net_profit,
        max_loss_with_fees_usd=max_loss_with_fees,
        risk_reward_ratio=risk_reward_ratio,
    )


def validate_profile_limits(profile: RiskProfile) -> list[str]:
    blockers: list[str] = []

    if profile.leverage > profile.max_leverage:
        blockers.append("leverage_above_limit")

    if profile.margin_usd > profile.max_margin_usd:
        blockers.append("margin_above_limit")

    if profile.notional_usd > profile.max_notional_usd:
        blockers.append("notional_above_limit")

    if profile.gross_stop_loss_usd > profile.max_trade_loss_usd:
        blockers.append("trade_loss_above_limit")

    return blockers


def validate_account_state(
    *,
    account_state: AccountRiskState,
    profile: RiskProfile,
) -> list[str]:
    blockers: list[str] = []

    if account_state.kill_switch_active:
        blockers.append("kill_switch_active")

    if account_state.daily_pnl_usd <= -profile.max_daily_loss_usd:
        blockers.append("max_daily_loss_reached")

    if account_state.consecutive_losses >= profile.max_consecutive_losses:
        blockers.append("max_consecutive_losses_reached")

    if account_state.open_positions >= profile.max_open_positions:
        blockers.append("max_open_positions_reached")

    if account_state.open_orders >= profile.max_open_orders:
        blockers.append("max_open_orders_reached")

    return blockers


def validate_signal(signal: TradingSignal, profile: RiskProfile) -> list[str]:
    blockers: list[str] = []

    if signal.decision != "ENTER":
        blockers.append("signal_not_enter")

    if signal.direction not in {"LONG", "SHORT"}:
        blockers.append("invalid_signal_direction")

    if signal.confidence < profile.min_confidence:
        blockers.append("signal_confidence_below_risk_minimum")

    return blockers


def validate_market_quality(signal: TradingSignal, profile: RiskProfile) -> list[str]:
    blockers: list[str] = []

    spread, liquidity = extract_market_quality(signal)

    if spread is not None and spread > profile.max_spread_pct:
        blockers.append("spread_above_risk_limit")

    if liquidity is not None and liquidity < profile.min_liquidity_usd:
        blockers.append("liquidity_below_risk_limit")

    return blockers


def assess_signal_risk(
    *,
    signal: TradingSignal | dict[str, Any],
    entry_price: float,
    account_state: AccountRiskState | None = None,
    profile: RiskProfile | None = None,
) -> RiskAssessment:
    parsed_signal = signal if isinstance(signal, TradingSignal) else TradingSignal.model_validate(signal)
    risk_profile = profile or get_default_risk_profile()
    state = account_state or AccountRiskState()

    blockers: list[str] = []
    reasons: list[str] = []

    blockers.extend(validate_signal(parsed_signal, risk_profile))
    blockers.extend(validate_profile_limits(risk_profile))
    blockers.extend(validate_account_state(account_state=state, profile=risk_profile))
    blockers.extend(validate_market_quality(parsed_signal, risk_profile))

    order_plan: OrderRiskPlan | None = None

    if parsed_signal.direction in {"LONG", "SHORT"}:
        try:
            order_plan = calculate_order_plan(
                direction=parsed_signal.direction,  # type: ignore[arg-type]
                entry_price=entry_price,
                timeframe=parsed_signal.timeframe,
                profile=risk_profile,
            )
        except ValueError:
            blockers.append("invalid_entry_price")

    if order_plan is not None:
        reasons.extend(
            [
                f"notional_usd:{order_plan.notional_usd:.2f}",
                f"margin_usd:{order_plan.margin_usd:.2f}",
                f"leverage:{order_plan.leverage:.2f}",
                f"tp_move_pct:{order_plan.tp_move_pct:.6f}",
                f"sl_move_pct:{order_plan.sl_move_pct:.6f}",
                f"risk_reward_ratio:{order_plan.risk_reward_ratio:.2f}",
            ]
        )

    decision: RiskDecision = "BLOCKED" if blockers else "APPROVED"

    return RiskAssessment(
        decision=decision,
        venue=risk_profile.venue,
        symbol=risk_profile.symbol,
        timeframe=parsed_signal.timeframe,
        direction=parsed_signal.direction,
        confidence=parsed_signal.confidence,
        blockers=blockers,
        reasons=reasons,
        order_plan=order_plan,
        account_state=state.to_dict(),
        signal=parsed_signal.model_dump(mode="json"),
    )


def assessment_to_dict(assessment: RiskAssessment) -> dict[str, Any]:
    return assessment.model_dump(mode="json")


def should_forward_to_executor(assessment: RiskAssessment) -> bool:
    return assessment.decision == "APPROVED" and assessment.order_plan is not None
# ============================================================
# Fase 5 — Final Signal Approval
# ============================================================

from risk.exposure import ExposureSnapshot, default_exposure_snapshot, exposure_pct
from risk.sizing import SizingPlan, calculate_fractional_kelly_position


class SignalApprovalResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "risk_manager"
    approved: bool

    venue: str = "binance_futures"
    symbol: str = "BTCUSDT"
    timeframe: str

    direction: str
    confidence: float

    blockers: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    sizing: dict[str, Any] | None = None
    exposure: dict[str, Any] | None = None

    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_timeframe_max_exposure_pct(timeframe: str) -> float:
    mapping = {
        "5m": "RISK_MAX_EXPOSURE_5M",
        "15m": "RISK_MAX_EXPOSURE_15M",
        "1h": "RISK_MAX_EXPOSURE_1H",
        "1d": "RISK_MAX_EXPOSURE_1D",
    }

    defaults = {
        "5m": 0.02,
        "15m": 0.04,
        "1h": 0.06,
        "1d": 0.08,
    }

    tf = timeframe.lower()

    return env_float(mapping.get(tf, "RISK_MAX_EXPOSURE_5M"), defaults.get(tf, 0.02))


def get_timeframe_min_edge(timeframe: str) -> float:
    mapping = {
        "5m": "RISK_MIN_EDGE_5M",
        "15m": "RISK_MIN_EDGE_15M",
        "1h": "RISK_MIN_EDGE_1H",
        "1d": "RISK_MIN_EDGE_1D",
    }

    defaults = {
        "5m": 0.035,
        "15m": 0.025,
        "1h": 0.020,
        "1d": 0.015,
    }

    tf = timeframe.lower()

    return env_float(mapping.get(tf, "RISK_MIN_EDGE_5M"), defaults.get(tf, 0.02))


def extract_edge_from_signal(signal_payload: dict[str, Any]) -> float | None:
    for key in ["edge", "edge_ratio", "expected_edge"]:
        value = safe_float(signal_payload.get(key))

        if value is not None:
            return value

    prediction = signal_payload.get("prediction")

    if isinstance(prediction, dict):
        expected_value = safe_float(prediction.get("expected_value_usd"))
        loss = env_float("RISK_GROSS_STOP_LOSS_USD", 1.05)

        if expected_value is not None and loss > 0:
            return expected_value / loss

    raw_features = signal_payload.get("raw_features")

    if isinstance(raw_features, dict):
        expected_value = safe_float(raw_features.get("expected_value_usd"))
        loss = env_float("RISK_GROSS_STOP_LOSS_USD", 1.05)

        if expected_value is not None and loss > 0:
            return expected_value / loss

    return None


def approve(
    signal: TradingSignal | dict[str, Any],
    *,
    risk_assessment: RiskAssessment | None = None,
    exposure_snapshot: ExposureSnapshot | None = None,
    market_liquidity_usd: float | None = None,
) -> bool:
    return approve_signal(
        signal,
        risk_assessment=risk_assessment,
        exposure_snapshot=exposure_snapshot,
        market_liquidity_usd=market_liquidity_usd,
    ).approved


def approve_signal(
    signal: TradingSignal | dict[str, Any],
    *,
    risk_assessment: RiskAssessment | None = None,
    exposure_snapshot: ExposureSnapshot | None = None,
    market_liquidity_usd: float | None = None,
) -> SignalApprovalResult:
    parsed_signal = signal if isinstance(signal, TradingSignal) else TradingSignal.model_validate(signal)
    payload = parsed_signal.model_dump(mode="json")

    snapshot = exposure_snapshot or default_exposure_snapshot()

    blockers: list[str] = []
    reasons: list[str] = []

    if parsed_signal.decision != "ENTER":
        blockers.append("signal_not_enter")

    if parsed_signal.direction not in {"LONG", "SHORT"}:
        blockers.append("invalid_direction")

    min_confidence = env_float("RISK_MIN_CONFIDENCE", 0.65)

    if parsed_signal.confidence < min_confidence:
        blockers.append("confidence_below_minimum")

    if risk_assessment is not None and risk_assessment.decision != "APPROVED":
        blockers.append("risk_assessment_not_approved")

    plan = risk_assessment.order_plan if risk_assessment is not None else None

    margin_usd = plan.margin_usd if plan is not None else env_float("RISK_MARGIN_USD", 20.0)
    max_loss_with_fees = (
        plan.max_loss_with_fees_usd
        if plan is not None
        else env_float("RISK_GROSS_STOP_LOSS_USD", 1.05)
    )

    bankroll = snapshot.total_bankroll_usd

    max_trade_risk_pct = env_float("RISK_MAX_TRADE_RISK_PCT", 0.01)
    trade_risk_pct = max_loss_with_fees / bankroll if bankroll > 0 else 1.0

    reasons.append(f"trade_risk_pct:{trade_risk_pct:.6f}")

    if trade_risk_pct > max_trade_risk_pct:
        blockers.append("trade_risk_above_limit")

    max_daily_loss_pct = env_float("RISK_MAX_DAILY_LOSS_PCT", 0.03)
    daily_loss_pct = abs(min(snapshot.daily_pnl_usd, 0.0)) / bankroll if bankroll > 0 else 1.0

    reasons.append(f"daily_loss_pct:{daily_loss_pct:.6f}")

    if daily_loss_pct >= max_daily_loss_pct:
        blockers.append("daily_loss_limit_reached")

    symbol = parsed_signal.symbol.upper()
    timeframe = parsed_signal.timeframe.lower()

    current_market_exposure = snapshot.exposure_per_market.get(symbol, 0.0)
    market_exposure_after = current_market_exposure + margin_usd

    max_market_exposure_pct = env_float("RISK_MAX_MARKET_EXPOSURE_PCT", 0.05)
    market_exposure_pct = exposure_pct(snapshot, market_exposure_after)

    reasons.append(f"market_exposure_pct_after:{market_exposure_pct:.6f}")

    if market_exposure_pct > max_market_exposure_pct:
        blockers.append("market_exposure_above_limit")

    current_timeframe_exposure = snapshot.exposure_by_timeframe.get(timeframe, 0.0)
    timeframe_exposure_after = current_timeframe_exposure + margin_usd

    max_timeframe_exposure_pct = get_timeframe_max_exposure_pct(timeframe)
    timeframe_exposure_pct = exposure_pct(snapshot, timeframe_exposure_after)

    reasons.append(f"timeframe_exposure_pct_after:{timeframe_exposure_pct:.6f}")

    if timeframe_exposure_pct > max_timeframe_exposure_pct:
        blockers.append("timeframe_exposure_above_limit")

    directional_sign = 1 if parsed_signal.direction == "LONG" else -1
    directional_after = snapshot.btc_directional_exposure_usd + directional_sign * margin_usd
    directional_pct = abs(directional_after) / bankroll if bankroll > 0 else 1.0

    max_directional_pct = env_float("RISK_MAX_BTC_DIRECTIONAL_EXPOSURE_PCT", 0.10)

    reasons.append(f"btc_directional_exposure_pct_after:{directional_pct:.6f}")

    if directional_pct > max_directional_pct:
        blockers.append("btc_directional_exposure_above_limit")

    edge = extract_edge_from_signal(payload)
    min_edge = get_timeframe_min_edge(timeframe)

    if edge is None:
        reasons.append("edge_not_available")

        if env_bool("RISK_REQUIRE_EDGE", False):
            blockers.append("edge_missing")
    else:
        reasons.append(f"edge:{edge:.6f}")

        if edge < min_edge:
            blockers.append("edge_below_timeframe_minimum")

    raw_features = payload.get("raw_features") or {}
    liquidity = market_liquidity_usd

    if liquidity is None:
        liquidity = safe_float(raw_features.get("binance_liquidity_usd"))

    if liquidity is None:
        liquidity = env_float("RISK_MIN_LIQUIDITY_USD", 50000.0)

    sizing_plan: SizingPlan | None = None

    if edge is not None and plan is not None:
        odds = plan.gross_take_profit_usd / plan.gross_stop_loss_usd

        sizing_plan = calculate_fractional_kelly_position(
            bankroll_usd=bankroll,
            edge=edge,
            odds=odds,
            market_liquidity_usd=liquidity,
        )

        reasons.extend(sizing_plan.reasons)

        for blocker in sizing_plan.blockers:
            blockers.append(f"sizing_{blocker}")

    approved = not blockers

    return SignalApprovalResult(
        approved=approved,
        venue=parsed_signal.venue,
        symbol=parsed_signal.symbol,
        timeframe=parsed_signal.timeframe,
        direction=parsed_signal.direction,
        confidence=parsed_signal.confidence,
        blockers=blockers,
        reasons=reasons,
        sizing=sizing_plan.model_dump(mode="json") if sizing_plan else None,
        exposure=snapshot.model_dump(mode="json"),
    )