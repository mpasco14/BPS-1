from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from portfolio_intelligence.exposure_ledger import ExposureLedgerSummary
from portfolio_intelligence.position_lifecycle import PositionLifecycleReport


load_dotenv()


ConcentrationStatus = Literal["PASS", "WARN", "FAIL"]


class ExposureConcentrationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/portfolio")

    max_total_notional_usd: float = 1000.0
    max_symbol_concentration_pct: float = 0.80
    max_timeframe_concentration_pct: float = 0.70
    max_leverage: int = 30
    max_open_positions: int = 3
    max_directional_bias_pct: float = 0.85


class ExposureConcentrationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "exposure_concentration_guard"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ConcentrationStatus
    passed: bool

    max_symbol_concentration_pct_seen: float = 0.0
    max_timeframe_concentration_pct_seen: float = 0.0
    directional_bias_pct: float = 0.0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    summary: dict[str, Any]
    lifecycle: dict[str, Any] | None = None
    config: dict[str, Any]


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


def load_exposure_concentration_config() -> ExposureConcentrationConfig:
    return ExposureConcentrationConfig(
        output_dir=Path(os.getenv("EXPOSURE_CONCENTRATION_OUTPUT_DIR", "artifacts/portfolio")),
        max_total_notional_usd=env_float("EXPOSURE_MAX_TOTAL_NOTIONAL_USD", 1000),
        max_symbol_concentration_pct=env_float("EXPOSURE_MAX_SYMBOL_CONCENTRATION_PCT", 0.80),
        max_timeframe_concentration_pct=env_float("EXPOSURE_MAX_TIMEFRAME_CONCENTRATION_PCT", 0.70),
        max_leverage=env_int("EXPOSURE_MAX_LEVERAGE", 30),
        max_open_positions=env_int("EXPOSURE_MAX_OPEN_POSITIONS", 3),
        max_directional_bias_pct=env_float("EXPOSURE_MAX_DIRECTIONAL_BIAS_PCT", 0.85),
    )


def max_concentration(values: dict[str, float], total_abs: float) -> float:
    if total_abs <= 0:
        return 0.0

    return max((abs(value) / total_abs for value in values.values()), default=0.0)


def directional_bias(summary: ExposureLedgerSummary) -> float:
    total = summary.total_abs_notional_usd

    if total <= 0:
        return 0.0

    dominant = max(summary.gross_long_notional_usd, summary.gross_short_notional_usd)

    return dominant / total


def evaluate_exposure_concentration(
    *,
    summary: ExposureLedgerSummary | dict[str, Any],
    lifecycle: PositionLifecycleReport | dict[str, Any] | None = None,
    config: ExposureConcentrationConfig | None = None,
) -> ExposureConcentrationReport:
    resolved_config = config or load_exposure_concentration_config()
    parsed_summary = summary if isinstance(summary, ExposureLedgerSummary) else ExposureLedgerSummary.model_validate(summary)

    parsed_lifecycle = None
    if lifecycle is not None:
        parsed_lifecycle = lifecycle if isinstance(lifecycle, PositionLifecycleReport) else PositionLifecycleReport.model_validate(lifecycle)

    blockers: list[str] = []
    warnings: list[str] = []

    if parsed_summary.total_abs_notional_usd > resolved_config.max_total_notional_usd:
        blockers.append("total_notional_above_limit")

    if parsed_summary.max_leverage_seen > resolved_config.max_leverage:
        blockers.append("leverage_above_limit")

    symbol_concentration = max_concentration(
        parsed_summary.exposure_by_symbol,
        parsed_summary.total_abs_notional_usd,
    )

    # Em estratégia focada apenas em BTCUSDT, concentração de 100% em um único símbolo é esperada.
    # Só vira blocker quando há mais de um símbolo e um deles domina acima do limite.
    if parsed_summary.symbols_count > 1:
        if symbol_concentration > resolved_config.max_symbol_concentration_pct:
            blockers.append("symbol_concentration_above_limit")
    elif parsed_summary.symbols_count == 1 and symbol_concentration > resolved_config.max_symbol_concentration_pct:
        warnings.append("single_symbol_concentration_expected")

    timeframe_concentration = max_concentration(
        parsed_summary.exposure_by_timeframe,
        parsed_summary.total_abs_notional_usd,
    )

    # Em uma posição única, concentração de timeframe também é esperada.
    # Só alertamos quando há mais de um timeframe e um timeframe domina.
    if parsed_summary.timeframes_count > 1:
        if timeframe_concentration > resolved_config.max_timeframe_concentration_pct:
            warnings.append("timeframe_concentration_above_limit")
    elif parsed_summary.timeframes_count == 1 and timeframe_concentration > resolved_config.max_timeframe_concentration_pct:
        warnings.append("single_timeframe_concentration_expected")

    bias = directional_bias(parsed_summary)

    # Uma posição única sempre terá viés direcional 100%.
    # Isso deve ser warning operacional, não blocker.
    if bias > resolved_config.max_directional_bias_pct:
        warnings.append("directional_bias_above_limit")

    if parsed_lifecycle is not None and parsed_lifecycle.open_positions_count > resolved_config.max_open_positions:
        blockers.append("open_positions_above_limit")

    passed = not blockers

    return ExposureConcentrationReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        max_symbol_concentration_pct_seen=round(symbol_concentration, 8),
        max_timeframe_concentration_pct_seen=round(timeframe_concentration, 8),
        directional_bias_pct=round(bias, 8),
        blockers=blockers,
        warnings=warnings,
        summary=parsed_summary.model_dump(mode="json"),
        lifecycle=parsed_lifecycle.model_dump(mode="json") if parsed_lifecycle else None,
        config=resolved_config.model_dump(mode="json"),
    )

def export_exposure_concentration_report(
    report: ExposureConcentrationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "exposure_concentration_latest",
) -> Path:
    config = load_exposure_concentration_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path