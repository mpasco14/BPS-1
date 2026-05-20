from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ops.decision_journal import DecisionJournalEntry
from ops.outcome_attribution import OutcomeAttributionReport


load_dotenv()


class LearningFeedbackRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "learning_feedback_dataset"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    decision_id: str
    trade_id: str | None = None

    timestamp: datetime | None = None
    symbol: str = "BTCUSDT"
    timeframe: str | None = None
    side: str | None = None

    final_decision: str
    outcome_category: str | None = None

    model_version: str | None = None
    model_probability: float | None = None
    model_confidence: float | None = None
    expected_value_usd: float | None = None
    ood_detected: bool = False

    data_quality_passed: bool | None = None
    risk_approved: bool | None = None
    execution_allowed: bool | None = None

    spread_pct: float | None = None
    liquidity_usd: float | None = None
    regime: str | None = None

    realized_net_pnl_usd: float | None = None
    is_win: bool | None = None
    target: int | None = None

    latency_ms: float | None = None
    expected_slippage_pct: float | None = None
    realized_slippage_pct: float | None = None

    reason_codes: list[str] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    labels: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def dataset_file_path() -> Path:
    return Path(
        os.getenv(
            "LEARNING_FEEDBACK_DATASET_FILE",
            "artifacts/learning/learning_feedback_dataset.jsonl",
        )
    )


def _as_decision(entry: DecisionJournalEntry | dict[str, Any]) -> DecisionJournalEntry:
    return entry if isinstance(entry, DecisionJournalEntry) else DecisionJournalEntry.model_validate(entry)


def _as_outcome(report: OutcomeAttributionReport | dict[str, Any] | None) -> OutcomeAttributionReport | None:
    if report is None:
        return None

    return report if isinstance(report, OutcomeAttributionReport) else OutcomeAttributionReport.model_validate(report)


def build_learning_feedback_row(
    *,
    decision: DecisionJournalEntry | dict[str, Any],
    outcome: OutcomeAttributionReport | dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> LearningFeedbackRow:
    resolved_decision = _as_decision(decision)
    resolved_outcome = _as_outcome(outcome)

    evidence = resolved_decision.evidence or {}
    outcome_input = resolved_outcome.input if resolved_outcome else {}

    net_pnl = resolved_outcome.net_pnl_usd if resolved_outcome else None
    is_win = resolved_outcome.is_win if resolved_outcome else None

    return LearningFeedbackRow(
        decision_id=resolved_decision.decision_id,
        trade_id=resolved_outcome.trade_id if resolved_outcome else outcome_input.get("trade_id"),
        timestamp=resolved_decision.created_at,
        symbol=resolved_decision.symbol,
        timeframe=resolved_decision.timeframe or evidence.get("timeframe"),
        side=resolved_decision.side,
        final_decision=resolved_decision.final_decision,
        outcome_category=resolved_outcome.category if resolved_outcome else None,
        model_version=evidence.get("model_version"),
        model_probability=evidence.get("model_probability"),
        model_confidence=evidence.get("model_confidence"),
        expected_value_usd=evidence.get("expected_value_usd"),
        ood_detected=bool(evidence.get("ood_detected", False)),
        data_quality_passed=evidence.get("data_quality_passed"),
        risk_approved=evidence.get("risk_approved"),
        execution_allowed=evidence.get("execution_allowed"),
        spread_pct=evidence.get("spread_pct"),
        liquidity_usd=evidence.get("liquidity_usd"),
        regime=evidence.get("regime") or outcome_input.get("regime"),
        realized_net_pnl_usd=net_pnl,
        is_win=is_win,
        target=1 if is_win is True else 0 if is_win is False else None,
        latency_ms=outcome_input.get("latency_ms"),
        expected_slippage_pct=outcome_input.get("expected_slippage_pct"),
        realized_slippage_pct=outcome_input.get("realized_slippage_pct"),
        reason_codes=resolved_decision.reason_codes,
        features={
            "technical_score": evidence.get("technical_score"),
            "onchain_score": evidence.get("onchain_score"),
            "sentiment_score": evidence.get("sentiment_score"),
            "microstructure_score": evidence.get("microstructure_score"),
            "spread_pct": evidence.get("spread_pct"),
            "liquidity_usd": evidence.get("liquidity_usd"),
            "regime": evidence.get("regime"),
        },
        labels={
            "target": 1 if is_win is True else 0 if is_win is False else None,
            "outcome_category": resolved_outcome.category if resolved_outcome else None,
            "net_pnl_usd": net_pnl,
        },
        metadata=metadata or {},
    )


def build_learning_feedback_dataset(
    *,
    decisions: list[DecisionJournalEntry | dict[str, Any]],
    outcomes_by_decision_id: dict[str, OutcomeAttributionReport | dict[str, Any]] | None = None,
) -> list[LearningFeedbackRow]:
    outcomes = outcomes_by_decision_id or {}
    rows: list[LearningFeedbackRow] = []

    for decision in decisions:
        resolved_decision = _as_decision(decision)
        outcome = outcomes.get(resolved_decision.decision_id)

        rows.append(
            build_learning_feedback_row(
                decision=resolved_decision,
                outcome=outcome,
            )
        )

    return rows


def export_learning_feedback_jsonl(
    rows: list[LearningFeedbackRow],
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or dataset_file_path())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def append_learning_feedback_row(
    row: LearningFeedbackRow,
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or dataset_file_path())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def load_learning_feedback_jsonl(
    path: str | Path | None = None,
) -> list[LearningFeedbackRow]:
    input_path = Path(path or dataset_file_path())

    if not input_path.exists():
        return []

    rows: list[LearningFeedbackRow] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            rows.append(LearningFeedbackRow.model_validate(json.loads(line)))

    return rows