from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


DecisionType = Literal["ENTER", "SKIP", "BLOCK", "CANCEL", "MONITOR"]
DecisionSource = Literal["signal_engine", "risk_manager", "execution", "manual", "system"]


class DecisionEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    signal_id: str | None = None
    model_version: str | None = None

    model_probability: float | None = None
    model_confidence: float | None = None
    expected_value_usd: float | None = None
    ood_detected: bool = False

    technical_score: float | None = None
    onchain_score: float | None = None
    sentiment_score: float | None = None
    microstructure_score: float | None = None

    data_quality_passed: bool = True
    data_quality_blockers: list[str] = Field(default_factory=list)

    risk_approved: bool = True
    risk_blockers: list[str] = Field(default_factory=list)

    execution_allowed: bool = True
    execution_blockers: list[str] = Field(default_factory=list)

    spread_pct: float | None = None
    liquidity_usd: float | None = None

    regime: str | None = None
    timeframe: str | None = None


class DecisionJournalEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "decision_journal"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    decision_id: str
    decision_source: DecisionSource = "system"

    symbol: str = "BTCUSDT"
    timeframe: str | None = None
    side: str | None = None

    final_decision: DecisionType
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str

    evidence: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def journal_file_path() -> Path:
    return Path(os.getenv("DECISION_JOURNAL_FILE", "artifacts/journal/decision_journal.jsonl"))


def build_reason_codes(evidence: DecisionEvidence) -> list[str]:
    reasons: list[str] = []

    if not evidence.data_quality_passed:
        reasons.append("DATA_QUALITY_FAILED")
        reasons.extend(evidence.data_quality_blockers)

    if evidence.ood_detected:
        reasons.append("MODEL_OOD")

    if evidence.expected_value_usd is not None and evidence.expected_value_usd <= 0:
        reasons.append("EXPECTED_VALUE_NOT_POSITIVE")

    if not evidence.risk_approved:
        reasons.append("RISK_REJECTED")
        reasons.extend(evidence.risk_blockers)

    if not evidence.execution_allowed:
        reasons.append("EXECUTION_BLOCKED")
        reasons.extend(evidence.execution_blockers)

    if not reasons:
        reasons.append("ALL_CHECKS_PASSED")

    return reasons


def infer_final_decision(evidence: DecisionEvidence) -> DecisionType:
    if not evidence.data_quality_passed:
        return "BLOCK"

    if evidence.ood_detected:
        return "SKIP"

    if evidence.expected_value_usd is not None and evidence.expected_value_usd <= 0:
        return "SKIP"

    if not evidence.risk_approved:
        return "BLOCK"

    if not evidence.execution_allowed:
        return "BLOCK"

    return "ENTER"


def build_explanation(
    *,
    decision: DecisionType,
    evidence: DecisionEvidence,
    reason_codes: list[str],
) -> str:
    if decision == "ENTER":
        return (
            "Entrada aprovada porque qualidade de dados, modelo, risco e execução "
            "não apresentaram bloqueios."
        )

    if decision == "SKIP":
        return f"Entrada ignorada por condição não favorável: {', '.join(reason_codes)}."

    if decision == "BLOCK":
        return f"Entrada bloqueada por regra de proteção: {', '.join(reason_codes)}."

    if decision == "CANCEL":
        return f"Ordem cancelada por regra operacional: {', '.join(reason_codes)}."

    return f"Decisão em monitoramento: {', '.join(reason_codes)}."


def build_decision_journal_entry(
    *,
    decision_id: str,
    symbol: str,
    side: str | None,
    evidence: DecisionEvidence | dict[str, Any],
    decision_source: DecisionSource = "system",
    final_decision: DecisionType | None = None,
    metadata: dict[str, Any] | None = None,
) -> DecisionJournalEntry:
    resolved_evidence = evidence if isinstance(evidence, DecisionEvidence) else DecisionEvidence.model_validate(evidence)

    decision = final_decision or infer_final_decision(resolved_evidence)
    reason_codes = build_reason_codes(resolved_evidence)

    return DecisionJournalEntry(
        decision_id=decision_id,
        decision_source=decision_source,
        symbol=symbol,
        timeframe=resolved_evidence.timeframe,
        side=side,
        final_decision=decision,
        reason_codes=reason_codes,
        explanation=build_explanation(
            decision=decision,
            evidence=resolved_evidence,
            reason_codes=reason_codes,
        ),
        evidence=resolved_evidence.model_dump(mode="json"),
        metadata=metadata or {},
    )


def append_decision_journal_entry(
    entry: DecisionJournalEntry,
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or journal_file_path())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return output_path


def load_decision_journal(
    path: str | Path | None = None,
) -> list[DecisionJournalEntry]:
    input_path = Path(path or journal_file_path())

    if not input_path.exists():
        return []

    entries: list[DecisionJournalEntry] = []

    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            entries.append(DecisionJournalEntry.model_validate(json.loads(line)))

    return entries