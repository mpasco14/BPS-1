from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


RampStatus = Literal["PASS", "WARN", "FAIL"]


class CapitalRampConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_dir: Path = Path("artifacts/ops")

    current_level: int = 0
    max_level: int = 4

    level_max_margin_usd: dict[int, float] = Field(
        default_factory=lambda: {
            0: 0.0,
            1: 20.0,
            2: 50.0,
            3: 100.0,
            4: 250.0,
        }
    )

    min_trades_to_advance: int = 30
    min_win_rate: float = 0.50
    min_profit_factor: float = 1.10
    max_drawdown_pct: float = 0.10
    max_ece: float = 0.15

    require_no_critical_alerts: bool = True
    allow_auto_advance: bool = False


class CapitalRampInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    trades_count: int = 0
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown_pct: float | None = None
    expected_calibration_error: float | None = None

    critical_alerts: int = 0
    current_margin_usd: float = 0.0


class CapitalRampCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: RampStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class CapitalRampReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "capital_ramp"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    current_level: int
    next_level: int | None = None
    current_max_margin_usd: float
    next_max_margin_usd: float | None = None

    advance_recommended: bool = False
    auto_advance_allowed: bool = False

    checks_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    blocking_fail_count: int

    inputs: dict[str, Any]
    checks: list[dict[str, Any]] = Field(default_factory=list)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_capital_ramp_config() -> CapitalRampConfig:
    levels = {
        0: env_float("CAPITAL_RAMP_LEVEL_0_MAX_MARGIN_USD", 0),
        1: env_float("CAPITAL_RAMP_LEVEL_1_MAX_MARGIN_USD", 20),
        2: env_float("CAPITAL_RAMP_LEVEL_2_MAX_MARGIN_USD", 50),
        3: env_float("CAPITAL_RAMP_LEVEL_3_MAX_MARGIN_USD", 100),
        4: env_float("CAPITAL_RAMP_LEVEL_4_MAX_MARGIN_USD", 250),
    }

    return CapitalRampConfig(
        enabled=env_bool("CAPITAL_RAMP_ENABLED", True),
        output_dir=Path(os.getenv("CAPITAL_RAMP_OUTPUT_DIR", "artifacts/ops")),
        current_level=env_int("CAPITAL_RAMP_CURRENT_LEVEL", 0),
        max_level=env_int("CAPITAL_RAMP_MAX_LEVEL", 4),
        level_max_margin_usd=levels,
        min_trades_to_advance=env_int("CAPITAL_RAMP_MIN_TRADES_TO_ADVANCE", 30),
        min_win_rate=env_float("CAPITAL_RAMP_MIN_WIN_RATE", 0.50),
        min_profit_factor=env_float("CAPITAL_RAMP_MIN_PROFIT_FACTOR", 1.10),
        max_drawdown_pct=env_float("CAPITAL_RAMP_MAX_DRAWDOWN_PCT", 0.10),
        max_ece=env_float("CAPITAL_RAMP_MAX_ECE", 0.15),
        require_no_critical_alerts=env_bool("CAPITAL_RAMP_REQUIRE_NO_CRITICAL_ALERTS", True),
        allow_auto_advance=env_bool("CAPITAL_RAMP_ALLOW_AUTO_ADVANCE", False),
    )


def make_check(
    *,
    code: str,
    status: RampStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> CapitalRampCheck:
    return CapitalRampCheck(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def evaluate_capital_ramp(
    *,
    inputs: CapitalRampInputs,
    config: CapitalRampConfig,
) -> list[CapitalRampCheck]:
    if not config.enabled:
        return [
            make_check(
                code="CAPITAL_RAMP_DISABLED",
                status="FAIL",
                title="Capital ramp desabilitado",
                message="CAPITAL_RAMP_ENABLED está falso.",
                value=False,
                expected=True,
                blocking=True,
            )
        ]

    checks: list[CapitalRampCheck] = []

    trades_ok = inputs.trades_count >= config.min_trades_to_advance
    win_ok = inputs.win_rate is not None and inputs.win_rate >= config.min_win_rate
    pf_ok = inputs.profit_factor is not None and inputs.profit_factor >= config.min_profit_factor
    dd_ok = inputs.max_drawdown_pct is not None and inputs.max_drawdown_pct <= config.max_drawdown_pct
    ece_ok = inputs.expected_calibration_error is not None and inputs.expected_calibration_error <= config.max_ece
    alerts_ok = inputs.critical_alerts == 0

    checks.append(
        make_check(
            code="TRADES_OK" if trades_ok else "TRADES_INSUFFICIENT",
            status="PASS" if trades_ok else "FAIL",
            title="Quantidade de trades",
            message="Valida se há amostra mínima para avançar nível.",
            value=inputs.trades_count,
            expected=f">={config.min_trades_to_advance}",
            blocking=not trades_ok,
        )
    )

    checks.append(
        make_check(
            code="WIN_RATE_OK" if win_ok else "WIN_RATE_LOW",
            status="PASS" if win_ok else "FAIL",
            title="Win rate",
            message="Valida win rate mínimo.",
            value=inputs.win_rate,
            expected=f">={config.min_win_rate}",
            blocking=not win_ok,
        )
    )

    checks.append(
        make_check(
            code="PROFIT_FACTOR_OK" if pf_ok else "PROFIT_FACTOR_LOW",
            status="PASS" if pf_ok else "FAIL",
            title="Profit factor",
            message="Valida profit factor mínimo.",
            value=inputs.profit_factor,
            expected=f">={config.min_profit_factor}",
            blocking=not pf_ok,
        )
    )

    checks.append(
        make_check(
            code="DRAWDOWN_OK" if dd_ok else "DRAWDOWN_HIGH",
            status="PASS" if dd_ok else "FAIL",
            title="Drawdown",
            message="Valida drawdown máximo.",
            value=inputs.max_drawdown_pct,
            expected=f"<={config.max_drawdown_pct}",
            blocking=not dd_ok,
        )
    )

    checks.append(
        make_check(
            code="ECE_OK" if ece_ok else "ECE_HIGH",
            status="PASS" if ece_ok else "FAIL",
            title="ECE",
            message="Valida calibração antes de aumentar capital.",
            value=inputs.expected_calibration_error,
            expected=f"<={config.max_ece}",
            blocking=not ece_ok,
        )
    )

    if config.require_no_critical_alerts:
        checks.append(
            make_check(
                code="NO_CRITICAL_ALERTS" if alerts_ok else "CRITICAL_ALERTS_PRESENT",
                status="PASS" if alerts_ok else "FAIL",
                title="Alertas críticos",
                message="Não pode aumentar capital com alertas críticos.",
                value=inputs.critical_alerts,
                expected=0,
                blocking=not alerts_ok,
            )
        )

    return checks


def build_capital_ramp_report(
    *,
    inputs: CapitalRampInputs | dict[str, Any],
    config: CapitalRampConfig | None = None,
) -> CapitalRampReport:
    resolved_config = config or load_capital_ramp_config()
    resolved_inputs = inputs if isinstance(inputs, CapitalRampInputs) else CapitalRampInputs.model_validate(inputs)

    checks = evaluate_capital_ramp(
        inputs=resolved_inputs,
        config=resolved_config,
    )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0

    current_level = resolved_config.current_level
    next_level = current_level + 1 if current_level < resolved_config.max_level else None

    return CapitalRampReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        current_level=current_level,
        next_level=next_level,
        current_max_margin_usd=resolved_config.level_max_margin_usd.get(current_level, 0.0),
        next_max_margin_usd=resolved_config.level_max_margin_usd.get(next_level) if next_level is not None else None,
        advance_recommended=passed and next_level is not None,
        auto_advance_allowed=passed and next_level is not None and resolved_config.allow_auto_advance,
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        inputs=resolved_inputs.model_dump(mode="json"),
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_capital_ramp_report(
    report: CapitalRampReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "capital_ramp_latest",
) -> Path:
    config = load_capital_ramp_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path