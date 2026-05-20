from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


OutcomeCategory = Literal[
    "WIN_BY_MODEL_EDGE",
    "WIN_BY_EXECUTION_OR_VOLATILITY",
    "VALID_STATISTICAL_LOSS",
    "MODEL_ERROR",
    "MODEL_OOD",
    "BAD_REGIME",
    "SLIPPAGE_HIGH",
    "LATENCY_ISSUE",
    "INVALID_ENTRY",
    "RISK_TOO_AGGRESSIVE",
    "UNKNOWN",
]


class TradeOutcomeInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    trade_id: str
    symbol: str = "BTCUSDT"
    timeframe: str | None = None
    side: str

    entry_price: float | None = None
    exit_price: float | None = None

    predicted_probability: float | None = None
    expected_value_usd: float | None = None
    model_ood: bool = False

    realized_pnl_usd: float
    fees_usd: float = 0.0

    expected_slippage_pct: float | None = None
    realized_slippage_pct: float | None = None

    latency_ms: float | None = None
    regime: str | None = None

    risk_reward_ratio: float | None = None
    max_loss_with_fees_usd: float | None = None


class OutcomeAttributionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "outcome_attribution"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    trade_id: str
    symbol: str
    timeframe: str | None = None
    side: str

    category: OutcomeCategory
    is_win: bool
    net_pnl_usd: float

    reasons: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    input: dict[str, Any]


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def slippage_error_pct(input_data: TradeOutcomeInput) -> float | None:
    if input_data.expected_slippage_pct is None or input_data.realized_slippage_pct is None:
        return None

    return abs(input_data.realized_slippage_pct - input_data.expected_slippage_pct)


def classify_trade_outcome(
    input_data: TradeOutcomeInput,
) -> tuple[OutcomeCategory, list[str], list[str]]:
    max_slippage_error = env_float("OUTCOME_MAX_ACCEPTABLE_SLIPPAGE_ERROR_PCT", 0.001)
    max_latency = env_float("OUTCOME_MAX_ACCEPTABLE_LATENCY_MS", 1000)
    high_confidence = env_float("OUTCOME_HIGH_CONFIDENCE_THRESHOLD", 0.65)

    net_pnl = input_data.realized_pnl_usd - input_data.fees_usd
    reasons: list[str] = []
    recommendations: list[str] = []

    slip_error = slippage_error_pct(input_data)

    if input_data.model_ood:
        reasons.append("model_marked_as_ood")
        recommendations.append("Bloquear ou reduzir operações quando OOD estiver ativo.")
        return "MODEL_OOD", reasons, recommendations

    if slip_error is not None and slip_error > max_slippage_error:
        reasons.append("realized_slippage_deviated_from_expected")
        recommendations.append("Revisar slippage máximo, limit price e cancelamento por timeout.")
        return "SLIPPAGE_HIGH", reasons, recommendations

    if input_data.latency_ms is not None and input_data.latency_ms > max_latency:
        reasons.append("latency_above_limit")
        recommendations.append("Revisar infraestrutura, conexão e tempo de roteamento.")
        return "LATENCY_ISSUE", reasons, recommendations

    if input_data.regime in {"UNTRADEABLE", "HIGH_VOLATILITY", "LOW_LIQUIDITY", "NEWS_SHOCK"}:
        reasons.append(f"bad_market_regime:{input_data.regime}")
        recommendations.append("Adicionar ou endurecer No-Trade Engine para esse regime.")
        return "BAD_REGIME", reasons, recommendations

    if input_data.expected_value_usd is not None and input_data.expected_value_usd <= 0:
        reasons.append("entry_had_non_positive_expected_value")
        recommendations.append("Bloquear entradas com EV não positivo.")
        return "INVALID_ENTRY", reasons, recommendations

    if net_pnl > 0:
        if (
            input_data.predicted_probability is not None
            and input_data.predicted_probability >= high_confidence
            and input_data.expected_value_usd is not None
            and input_data.expected_value_usd > 0
        ):
            reasons.append("win_aligned_with_model_edge")
            recommendations.append("Registrar padrão vencedor no feedback dataset.")
            return "WIN_BY_MODEL_EDGE", reasons, recommendations

        reasons.append("win_not_strongly_explained_by_model_edge")
        recommendations.append("Revisar se o ganho veio de volatilidade, execução ou sorte estatística.")
        return "WIN_BY_EXECUTION_OR_VOLATILITY", reasons, recommendations

    if input_data.predicted_probability is not None and input_data.predicted_probability >= high_confidence:
        reasons.append("high_confidence_prediction_lost")
        recommendations.append("Revisar calibração, features e regime do modelo.")
        return "MODEL_ERROR", reasons, recommendations

    if input_data.max_loss_with_fees_usd is not None and abs(net_pnl) > input_data.max_loss_with_fees_usd:
        reasons.append("loss_exceeded_expected_max_loss")
        recommendations.append("Auditar stop loss, slippage e execução.")
        return "RISK_TOO_AGGRESSIVE", reasons, recommendations

    reasons.append("loss_within_expected_distribution")
    recommendations.append("Registrar como perda estatística válida; não ajustar modelo isoladamente.")
    return "VALID_STATISTICAL_LOSS", reasons, recommendations


def build_outcome_attribution_report(
    input_data: TradeOutcomeInput | dict[str, Any],
) -> OutcomeAttributionReport:
    resolved_input = input_data if isinstance(input_data, TradeOutcomeInput) else TradeOutcomeInput.model_validate(input_data)

    category, reasons, recommendations = classify_trade_outcome(resolved_input)
    net_pnl = resolved_input.realized_pnl_usd - resolved_input.fees_usd

    return OutcomeAttributionReport(
        trade_id=resolved_input.trade_id,
        symbol=resolved_input.symbol,
        timeframe=resolved_input.timeframe,
        side=resolved_input.side,
        category=category,
        is_win=net_pnl > 0,
        net_pnl_usd=net_pnl,
        reasons=reasons,
        recommendations=recommendations,
        input=resolved_input.model_dump(mode="json"),
    )


def export_outcome_attribution_report(
    report: OutcomeAttributionReport,
    *,
    output_dir: str | Path | None = None,
    name: str | None = None,
) -> Path:
    path = Path(output_dir or os.getenv("OUTCOME_ATTRIBUTION_OUTPUT_DIR", "artifacts/journal"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = (name or f"outcome_{report.trade_id}").replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path