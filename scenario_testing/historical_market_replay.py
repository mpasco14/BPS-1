from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from scenario_testing.scenario_models import (
    MarketCandle,
    ReplayStepResult,
    ScenarioTestReport,
    confidence_from_move,
    direction_from_price_change,
    edge_from_move,
    env_float,
    env_int,
    pct_change,
)
from system_integration.execution_contract import RiskApprovalDecision
from system_integration.sentiment_journal_integration import SentimentNoTradeInput, integrate_sentiment_no_trade_journal
from system_integration.signal_risk_execution_adapter import SignalDecision, adapt_signal_to_risk_execution


class HistoricalReplayConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/scenario_testing")

    initial_equity_usd: float = 1000.0
    default_notional_usd: float = 60.0
    default_margin_usd: float = 5.0
    default_leverage: int = 12

    min_abs_move_for_signal_pct: float = 0.002
    max_drawdown_pct: float = 0.03


def load_historical_replay_config() -> HistoricalReplayConfig:
    return HistoricalReplayConfig(
        output_dir=Path(os.getenv("HISTORICAL_REPLAY_OUTPUT_DIR", "artifacts/scenario_testing")),
        initial_equity_usd=env_float("HISTORICAL_REPLAY_INITIAL_EQUITY_USD", 1000),
        default_notional_usd=env_float("HISTORICAL_REPLAY_DEFAULT_NOTIONAL_USD", 60),
        default_margin_usd=env_float("HISTORICAL_REPLAY_DEFAULT_MARGIN_USD", 5),
        default_leverage=env_int("HISTORICAL_REPLAY_DEFAULT_LEVERAGE", 12),
        min_abs_move_for_signal_pct=env_float("HISTORICAL_REPLAY_MIN_ABS_MOVE_FOR_SIGNAL_PCT", 0.002),
        max_drawdown_pct=env_float("HISTORICAL_REPLAY_MAX_DRAWDOWN_PCT", 0.03),
    )


def estimate_step_pnl_usd(
    *,
    direction: str,
    change_pct: float,
    notional_usd: float,
) -> float:
    if direction == "BUY":
        return notional_usd * change_pct

    if direction == "SELL":
        return notional_usd * (-change_pct)

    return 0.0


def run_historical_market_replay(
    *,
    candles: list[MarketCandle | dict[str, Any]],
    scenario_name: str = "historical_market_replay",
    config: HistoricalReplayConfig | None = None,
    metadata: dict[str, Any] | None = None,
) -> ScenarioTestReport:
    resolved_config = config or load_historical_replay_config()

    parsed_candles = [
        item if isinstance(item, MarketCandle) else MarketCandle.model_validate(item)
        for item in candles
    ]
    parsed_candles = sorted(parsed_candles, key=lambda item: item.timestamp)

    blockers: list[str] = []
    warnings: list[str] = []
    steps: list[ReplayStepResult] = []

    if len(parsed_candles) < 2:
        return ScenarioTestReport(
            scenario_name=scenario_name,
            scenario_kind="historical_replay",
            status="FAIL",
            passed=False,
            candles_count=len(parsed_candles),
            blockers=["not_enough_candles_for_replay"],
            recommendations=["Fornecer pelo menos 2 candles para replay."],
            metadata=metadata or {},
        )

    equity = resolved_config.initial_equity_usd
    peak_equity = equity
    max_drawdown = 0.0
    cumulative_pnl = 0.0

    for index in range(1, len(parsed_candles)):
        previous = parsed_candles[index - 1]
        current = parsed_candles[index]

        change_pct = pct_change(previous.close, current.close)
        direction = direction_from_price_change(
            change_pct=change_pct,
            threshold_pct=resolved_config.min_abs_move_for_signal_pct,
        )
        confidence = confidence_from_move(change_pct)
        edge = edge_from_move(change_pct)

        step_blockers: list[str] = []
        step_warnings: list[str] = []

        sentiment = integrate_sentiment_no_trade_journal(
            sentiment=SentimentNoTradeInput(
                asset=current.symbol,
                timeframe=current.timeframe,
                sentiment_index=current.sentiment_index,
                fear_greed_value=current.fear_greed_value,
                confidence=current.sentiment_confidence,
                regime=current.sentiment_regime,
                panic_score=90 if current.sentiment_regime == "extreme_fear" else 0,
                euphoria_score=95 if current.sentiment_regime == "extreme_greed" else 0,
            ),
            metadata={"scenario_name": scenario_name, "step_index": index},
        )

        if not sentiment.approved_for_signal:
            step_blockers.extend([f"sentiment:{item}" for item in sentiment.blockers])

        signal = SignalDecision(
            symbol=current.symbol,
            timeframe=current.timeframe,
            direction=direction,
            probability=0.50 + min(0.45, abs(change_pct) * 20),
            confidence=confidence,
            edge=edge,
            suggested_quantity=0.001,
            suggested_price=current.close,
            suggested_notional_usd=resolved_config.default_notional_usd,
            suggested_margin_usd=resolved_config.default_margin_usd,
            suggested_leverage=resolved_config.default_leverage,
            metadata={
                "scenario_name": scenario_name,
                "step_index": index,
                "regime": current.regime,
                "news_event": current.news_event,
            },
        )

        risk = RiskApprovalDecision(
            approved=True,
            risk_score=0.25,
            metadata={
                "scenario_name": scenario_name,
                "step_index": index,
            },
        )

        pipeline = adapt_signal_to_risk_execution(
            signal=signal,
            risk_decision=risk,
            execution_mode="paper",
            live_submission_allowed=False,
            human_approval_valid=False,
            production_guard_passed=False,
            safe_mode_active=False,
            kill_switch_active=False,
        )

        if not pipeline.approved:
            step_blockers.extend(pipeline.blockers)

        step_warnings.extend(pipeline.warnings)
        step_warnings.extend([f"sentiment:{item}" for item in sentiment.warnings])

        approved = pipeline.approved and not step_blockers and direction != "HOLD"

        step_pnl = estimate_step_pnl_usd(
            direction=direction if approved else "HOLD",
            change_pct=change_pct,
            notional_usd=resolved_config.default_notional_usd,
        )

        cumulative_pnl += step_pnl
        equity = resolved_config.initial_equity_usd + cumulative_pnl
        peak_equity = max(peak_equity, equity)

        drawdown = 0.0
        if peak_equity > 0:
            drawdown = max(0.0, (peak_equity - equity) / peak_equity)

        max_drawdown = max(max_drawdown, drawdown)

        if drawdown > resolved_config.max_drawdown_pct:
            step_blockers.append("replay_drawdown_above_limit")

        step = ReplayStepResult(
            step_index=index,
            timestamp=current.timestamp,
            symbol=current.symbol,
            timeframe=current.timeframe,
            close=current.close,
            price_change_pct=round(change_pct, 8),
            direction=direction,
            confidence=confidence,
            edge=edge,
            approved=approved,
            blocked=bool(step_blockers),
            dry_run=True,
            step_pnl_usd=round(step_pnl, 8),
            cumulative_pnl_usd=round(cumulative_pnl, 8),
            equity_usd=round(equity, 8),
            drawdown_pct=round(drawdown, 8),
            blockers=step_blockers,
            warnings=step_warnings,
            components={
                "sentiment": sentiment.model_dump(mode="json"),
                "pipeline": pipeline.model_dump(mode="json"),
            },
        )
        steps.append(step)

    blockers.extend(
        sorted({item for step in steps for item in step.blockers if item == "replay_drawdown_above_limit"})
    )

    warnings.extend(
        sorted({item for step in steps for item in step.warnings})
    )

    approved_signals = sum(1 for step in steps if step.approved)
    blocked_signals = sum(1 for step in steps if step.blocked)
    hold_signals = sum(1 for step in steps if step.direction == "HOLD")

    passed = not blockers

    status = "PASS"
    if not passed:
        status = "FAIL"
    elif warnings:
        status = "WARN"

    return ScenarioTestReport(
        scenario_name=scenario_name,
        scenario_kind="historical_replay",
        status=status,
        passed=passed,
        candles_count=len(parsed_candles),
        steps_count=len(steps),
        approved_signals_count=approved_signals,
        blocked_signals_count=blocked_signals,
        hold_signals_count=hold_signals,
        total_pnl_usd=round(cumulative_pnl, 8),
        final_equity_usd=round(equity, 8),
        max_drawdown_pct=round(max_drawdown, 8),
        blockers=blockers,
        warnings=warnings,
        recommendations=[
            "Replay aprovado apenas para validação offline.",
            "Não usar resultado de replay como garantia de lucro futuro.",
        ],
        steps=[step.model_dump(mode="json") for step in steps],
        metadata=metadata or {},
    )