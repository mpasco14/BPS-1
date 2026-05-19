"""
Testnet quality gate.

Responsabilidades:
- Avaliar qualidade de uma sessão de testnet.
- Bloquear avanço se fill rate, rejeições, cancelamentos, slippage ou latência estiverem ruins.
- Não envia ordens.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ops.testnet_session import TestnetSessionReport


load_dotenv()


QualityStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetQualityConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    min_fill_rate: float = 0.60
    max_rejection_rate: float = 0.10
    max_cancel_rate: float = 0.25
    max_avg_latency_ms: float = 1000
    max_avg_slippage_error_pct: float = 0.001
    require_positive_pnl: bool = False


class TestnetQualityCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: QualityStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class TestnetQualityReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_quality_gate"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    checks_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    blocking_fail_count: int

    session_name: str
    metrics: dict[str, Any]
    checks: list[dict[str, Any]] = Field(default_factory=list)


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


def load_testnet_quality_config() -> TestnetQualityConfig:
    return TestnetQualityConfig(
        min_fill_rate=env_float("TESTNET_SESSION_MIN_FILL_RATE", 0.60),
        max_rejection_rate=env_float("TESTNET_SESSION_MAX_REJECTION_RATE", 0.10),
        max_cancel_rate=env_float("TESTNET_SESSION_MAX_CANCEL_RATE", 0.25),
        max_avg_latency_ms=env_float("TESTNET_SESSION_MAX_AVG_LATENCY_MS", 1000),
        max_avg_slippage_error_pct=env_float("TESTNET_SESSION_MAX_AVG_SLIPPAGE_ERROR_PCT", 0.001),
        require_positive_pnl=env_bool("TESTNET_SESSION_REQUIRE_POSITIVE_PNL", False),
    )


def make_check(
    *,
    code: str,
    status: QualityStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> TestnetQualityCheck:
    return TestnetQualityCheck(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def metric(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_testnet_quality(
    *,
    report: TestnetSessionReport | dict[str, Any],
    config: TestnetQualityConfig | None = None,
) -> TestnetQualityReport:
    resolved_report = report if isinstance(report, TestnetSessionReport) else TestnetSessionReport.model_validate(report)
    resolved_config = config or load_testnet_quality_config()

    metrics = resolved_report.metrics
    checks: list[TestnetQualityCheck] = []

    fill_rate = metric(metrics, "fill_rate")
    rejection_rate = metric(metrics, "rejection_rate")
    cancel_rate = metric(metrics, "cancel_rate")
    avg_latency = metric(metrics, "average_latency_ms")
    avg_slippage_error = metric(metrics, "average_slippage_error_pct")
    net_pnl = metric(metrics, "net_pnl_usd")

    checks.append(
        make_check(
            code="FILL_RATE_OK" if fill_rate is not None and fill_rate >= resolved_config.min_fill_rate else "FILL_RATE_LOW",
            status="PASS" if fill_rate is not None and fill_rate >= resolved_config.min_fill_rate else "FAIL",
            title="Fill rate",
            message="Valida taxa de fills da sessão.",
            value=fill_rate,
            expected=f">={resolved_config.min_fill_rate}",
            blocking=not (fill_rate is not None and fill_rate >= resolved_config.min_fill_rate),
        )
    )

    checks.append(
        make_check(
            code="REJECTION_RATE_OK" if rejection_rate is not None and rejection_rate <= resolved_config.max_rejection_rate else "REJECTION_RATE_HIGH",
            status="PASS" if rejection_rate is not None and rejection_rate <= resolved_config.max_rejection_rate else "FAIL",
            title="Rejection rate",
            message="Valida taxa de rejeições.",
            value=rejection_rate,
            expected=f"<={resolved_config.max_rejection_rate}",
            blocking=not (rejection_rate is not None and rejection_rate <= resolved_config.max_rejection_rate),
        )
    )

    checks.append(
        make_check(
            code="CANCEL_RATE_OK" if cancel_rate is not None and cancel_rate <= resolved_config.max_cancel_rate else "CANCEL_RATE_HIGH",
            status="PASS" if cancel_rate is not None and cancel_rate <= resolved_config.max_cancel_rate else "WARN",
            title="Cancel rate",
            message="Valida taxa de cancelamentos.",
            value=cancel_rate,
            expected=f"<={resolved_config.max_cancel_rate}",
            blocking=False,
        )
    )

    if avg_latency is not None:
        checks.append(
            make_check(
                code="LATENCY_OK" if avg_latency <= resolved_config.max_avg_latency_ms else "LATENCY_HIGH",
                status="PASS" if avg_latency <= resolved_config.max_avg_latency_ms else "WARN",
                title="Latency",
                message="Valida latência média.",
                value=avg_latency,
                expected=f"<={resolved_config.max_avg_latency_ms}",
            )
        )
    else:
        checks.append(
            make_check(
                code="LATENCY_MISSING",
                status="WARN",
                title="Latency ausente",
                message="Latência média ausente.",
            )
        )

    if avg_slippage_error is not None:
        checks.append(
            make_check(
                code="SLIPPAGE_ERROR_OK" if avg_slippage_error <= resolved_config.max_avg_slippage_error_pct else "SLIPPAGE_ERROR_HIGH",
                status="PASS" if avg_slippage_error <= resolved_config.max_avg_slippage_error_pct else "WARN",
                title="Slippage error",
                message="Valida erro médio de slippage.",
                value=avg_slippage_error,
                expected=f"<={resolved_config.max_avg_slippage_error_pct}",
            )
        )
    else:
        checks.append(
            make_check(
                code="SLIPPAGE_ERROR_MISSING",
                status="WARN",
                title="Slippage error ausente",
                message="Erro médio de slippage ausente.",
            )
        )

    if resolved_config.require_positive_pnl:
        checks.append(
            make_check(
                code="PNL_POSITIVE" if net_pnl is not None and net_pnl > 0 else "PNL_NOT_POSITIVE",
                status="PASS" if net_pnl is not None and net_pnl > 0 else "FAIL",
                title="PnL positivo",
                message="Valida PnL líquido positivo.",
                value=net_pnl,
                expected=">0",
                blocking=not (net_pnl is not None and net_pnl > 0),
            )
        )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    passed = blocking_fail_count == 0

    return TestnetQualityReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        session_name=resolved_report.session_name,
        metrics=metrics,
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_testnet_quality_report(
    report: TestnetQualityReport,
    *,
    output_dir: str | Path = "artifacts/testnet",
    name: str = "testnet_quality_latest",
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path