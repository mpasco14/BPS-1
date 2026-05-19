"""
Testnet warm-up evaluation.

Responsabilidades:
- Avaliar se o sistema completou um período mínimo de paper/testnet.
- Verificar trades, fill rate, slippage, alertas e checks operacionais.
- Gerar relatório auditável.
- Não executa ordens.
- Não habilita live trading.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


WarmupStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetWarmupConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_dir: Path = Path("artifacts/ops")

    min_days: int = 14
    min_trades: int = 50
    min_fill_rate: float = 0.60
    max_slippage_error_pct: float = 0.001

    max_critical_alerts: int = 0
    max_warning_alerts: int = 5

    require_ops_check_pass: bool = True
    require_runbook_pass: bool = True


class TestnetWarmupInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    days_completed: int = 0
    trades_count: int = 0

    fill_rate: float | None = None
    average_slippage_error_pct: float | None = None

    critical_alerts: int = 0
    warning_alerts: int = 0

    ops_check_passed: bool | None = None
    runbook_passed: bool | None = None

    notes: str | None = None


class TestnetWarmupCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: WarmupStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class TestnetWarmupReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_warmup"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

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


def load_testnet_warmup_config() -> TestnetWarmupConfig:
    return TestnetWarmupConfig(
        enabled=env_bool("TESTNET_WARMUP_ENABLED", True),
        output_dir=Path(os.getenv("TESTNET_WARMUP_OUTPUT_DIR", "artifacts/ops")),
        min_days=env_int("TESTNET_WARMUP_MIN_DAYS", 14),
        min_trades=env_int("TESTNET_WARMUP_MIN_TRADES", 50),
        min_fill_rate=env_float("TESTNET_WARMUP_MIN_FILL_RATE", 0.60),
        max_slippage_error_pct=env_float("TESTNET_WARMUP_MAX_SLIPPAGE_ERROR_PCT", 0.001),
        max_critical_alerts=env_int("TESTNET_WARMUP_MAX_CRITICAL_ALERTS", 0),
        max_warning_alerts=env_int("TESTNET_WARMUP_MAX_WARNING_ALERTS", 5),
        require_ops_check_pass=env_bool("TESTNET_WARMUP_REQUIRE_OPS_CHECK_PASS", True),
        require_runbook_pass=env_bool("TESTNET_WARMUP_REQUIRE_RUNBOOK_PASS", True),
    )


def make_check(
    *,
    code: str,
    status: WarmupStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> TestnetWarmupCheck:
    return TestnetWarmupCheck(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def latest_file(directory: str | Path, pattern: str) -> Path | None:
    path = Path(directory)

    if not path.exists():
        return None

    files = [item for item in path.glob(pattern) if item.is_file()]

    if not files:
        return None

    return max(files, key=lambda item: item.stat().st_mtime)


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_inputs_from_artifacts() -> TestnetWarmupInputs:
    paper_report = load_json(latest_file("artifacts/paper_trading", "*_summary.json"))
    alerts_report = load_json(latest_file("artifacts/alerts", "*.json"))
    ops_report = load_json(latest_file("artifacts/ops", "ops_*.json"))
    runbook_report = load_json(latest_file("artifacts/ops", "*runbook*.json"))

    paper_metrics = (paper_report or {}).get("metrics") or {}

    return TestnetWarmupInputs(
        trades_count=int(
            paper_metrics.get("simulated_trades", 0)
            or paper_metrics.get("routed_orders", 0)
            or 0
        ),
        fill_rate=safe_float(paper_metrics.get("fill_rate")),
        average_slippage_error_pct=safe_float(paper_metrics.get("average_slippage_error_pct")),
        critical_alerts=int((alerts_report or {}).get("critical_count", 0) or 0),
        warning_alerts=int((alerts_report or {}).get("warning_count", 0) or 0),
        ops_check_passed=(ops_report or {}).get("passed"),
        runbook_passed=(runbook_report or {}).get("passed"),
    )


def evaluate_testnet_warmup(
    *,
    inputs: TestnetWarmupInputs,
    config: TestnetWarmupConfig,
) -> list[TestnetWarmupCheck]:
    if not config.enabled:
        return [
            make_check(
                code="TESTNET_WARMUP_DISABLED",
                status="FAIL",
                title="Testnet warm-up desabilitado",
                message="TESTNET_WARMUP_ENABLED está falso.",
                value=False,
                expected=True,
                blocking=True,
            )
        ]

    checks: list[TestnetWarmupCheck] = []

    if inputs.days_completed >= config.min_days:
        checks.append(
            make_check(
                code="WARMUP_DAYS_OK",
                status="PASS",
                title="Dias de warm-up suficientes",
                message="O período mínimo de warm-up foi atingido.",
                value=inputs.days_completed,
                expected=f">={config.min_days}",
            )
        )
    else:
        checks.append(
            make_check(
                code="WARMUP_DAYS_INSUFFICIENT",
                status="FAIL",
                title="Dias de warm-up insuficientes",
                message="O período mínimo de warm-up ainda não foi atingido.",
                value=inputs.days_completed,
                expected=f">={config.min_days}",
                blocking=True,
            )
        )

    if inputs.trades_count >= config.min_trades:
        checks.append(
            make_check(
                code="WARMUP_TRADES_OK",
                status="PASS",
                title="Trades suficientes",
                message="Quantidade mínima de trades foi atingida.",
                value=inputs.trades_count,
                expected=f">={config.min_trades}",
            )
        )
    else:
        checks.append(
            make_check(
                code="WARMUP_TRADES_INSUFFICIENT",
                status="FAIL",
                title="Trades insuficientes",
                message="Quantidade de trades abaixo do mínimo.",
                value=inputs.trades_count,
                expected=f">={config.min_trades}",
                blocking=True,
            )
        )

    if inputs.fill_rate is not None and inputs.fill_rate >= config.min_fill_rate:
        checks.append(
            make_check(
                code="WARMUP_FILL_RATE_OK",
                status="PASS",
                title="Fill rate OK",
                message="Fill rate acima do mínimo.",
                value=inputs.fill_rate,
                expected=f">={config.min_fill_rate}",
            )
        )
    else:
        checks.append(
            make_check(
                code="WARMUP_FILL_RATE_LOW",
                status="FAIL",
                title="Fill rate baixo",
                message="Fill rate abaixo do mínimo ou ausente.",
                value=inputs.fill_rate,
                expected=f">={config.min_fill_rate}",
                blocking=True,
            )
        )

    if (
        inputs.average_slippage_error_pct is not None
        and inputs.average_slippage_error_pct <= config.max_slippage_error_pct
    ):
        checks.append(
            make_check(
                code="WARMUP_SLIPPAGE_OK",
                status="PASS",
                title="Slippage OK",
                message="Erro médio de slippage dentro do limite.",
                value=inputs.average_slippage_error_pct,
                expected=f"<={config.max_slippage_error_pct}",
            )
        )
    else:
        checks.append(
            make_check(
                code="WARMUP_SLIPPAGE_HIGH",
                status="WARN",
                title="Slippage alto ou ausente",
                message="Erro médio de slippage acima do limite ou ausente.",
                value=inputs.average_slippage_error_pct,
                expected=f"<={config.max_slippage_error_pct}",
            )
        )

    if inputs.critical_alerts <= config.max_critical_alerts:
        checks.append(
            make_check(
                code="WARMUP_CRITICAL_ALERTS_OK",
                status="PASS",
                title="Sem alertas críticos excessivos",
                message="Quantidade de alertas críticos dentro do limite.",
                value=inputs.critical_alerts,
                expected=f"<={config.max_critical_alerts}",
            )
        )
    else:
        checks.append(
            make_check(
                code="WARMUP_CRITICAL_ALERTS_HIGH",
                status="FAIL",
                title="Alertas críticos excessivos",
                message="Quantidade de alertas críticos acima do limite.",
                value=inputs.critical_alerts,
                expected=f"<={config.max_critical_alerts}",
                blocking=True,
            )
        )

    if inputs.warning_alerts <= config.max_warning_alerts:
        checks.append(
            make_check(
                code="WARMUP_WARNING_ALERTS_OK",
                status="PASS",
                title="Warnings dentro do limite",
                message="Quantidade de warnings dentro do limite.",
                value=inputs.warning_alerts,
                expected=f"<={config.max_warning_alerts}",
            )
        )
    else:
        checks.append(
            make_check(
                code="WARMUP_WARNING_ALERTS_HIGH",
                status="WARN",
                title="Warnings elevados",
                message="Quantidade de warnings acima do limite.",
                value=inputs.warning_alerts,
                expected=f"<={config.max_warning_alerts}",
            )
        )

    if config.require_ops_check_pass:
        if inputs.ops_check_passed is True:
            checks.append(
                make_check(
                    code="WARMUP_OPS_CHECK_OK",
                    status="PASS",
                    title="Ops check aprovado",
                    message="Ops check passou.",
                    value=True,
                    expected=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code="WARMUP_OPS_CHECK_FAIL",
                    status="FAIL",
                    title="Ops check não aprovado",
                    message="Ops check não passou ou está ausente.",
                    value=inputs.ops_check_passed,
                    expected=True,
                    blocking=True,
                )
            )

    if config.require_runbook_pass:
        if inputs.runbook_passed is True:
            checks.append(
                make_check(
                    code="WARMUP_RUNBOOK_OK",
                    status="PASS",
                    title="Runbook aprovado",
                    message="Runbook operacional passou.",
                    value=True,
                    expected=True,
                )
            )
        else:
            checks.append(
                make_check(
                    code="WARMUP_RUNBOOK_FAIL",
                    status="FAIL",
                    title="Runbook não aprovado",
                    message="Runbook operacional não passou ou está ausente.",
                    value=inputs.runbook_passed,
                    expected=True,
                    blocking=True,
                )
            )

    return checks


def build_testnet_warmup_report(
    *,
    inputs: TestnetWarmupInputs | dict[str, Any] | None = None,
    config: TestnetWarmupConfig | None = None,
) -> TestnetWarmupReport:
    resolved_config = config or load_testnet_warmup_config()

    if inputs is None:
        resolved_inputs = extract_inputs_from_artifacts()
    elif isinstance(inputs, TestnetWarmupInputs):
        resolved_inputs = inputs
    else:
        resolved_inputs = TestnetWarmupInputs.model_validate(inputs)

    checks = evaluate_testnet_warmup(
        inputs=resolved_inputs,
        config=resolved_config,
    )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0

    return TestnetWarmupReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        inputs=resolved_inputs.model_dump(mode="json"),
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_testnet_warmup_report(
    report: TestnetWarmupReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_warmup_latest",
) -> Path:
    config = load_testnet_warmup_config()
    resolved_output_dir = Path(output_dir or config.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    path = resolved_output_dir / f"{safe_name}.json"

    path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path