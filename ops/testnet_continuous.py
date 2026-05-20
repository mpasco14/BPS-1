from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


class TestnetContinuousConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet")

    min_sessions: int = 5
    min_trades: int = 50
    min_fill_rate: float = 0.60
    max_rejection_rate: float = 0.10
    max_cancel_rate: float = 0.25


class TestnetContinuousReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_continuous"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    sessions_count: int
    trades_count: int

    average_fill_rate: float = 0.0
    average_rejection_rate: float = 0.0
    average_cancel_rate: float = 0.0
    total_net_pnl_usd: float = 0.0

    checks: list[dict[str, Any]] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)


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


def load_testnet_continuous_config() -> TestnetContinuousConfig:
    return TestnetContinuousConfig(
        output_dir=Path(os.getenv("TESTNET_CONTINUOUS_OUTPUT_DIR", "artifacts/testnet")),
        min_sessions=env_int("TESTNET_CONTINUOUS_MIN_SESSIONS", 5),
        min_trades=env_int("TESTNET_CONTINUOUS_MIN_TRADES", 50),
        min_fill_rate=env_float("TESTNET_CONTINUOUS_MIN_FILL_RATE", 0.60),
        max_rejection_rate=env_float("TESTNET_CONTINUOUS_MAX_REJECTION_RATE", 0.10),
        max_cancel_rate=env_float("TESTNET_CONTINUOUS_MAX_CANCEL_RATE", 0.25),
    )


def load_session_summaries(directory: str | Path = "artifacts/testnet") -> list[dict[str, Any]]:
    path = Path(directory)

    if not path.exists():
        return []

    summaries: list[dict[str, Any]] = []

    for file_path in sorted(path.glob("*_summary.json")):
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        payload["_file"] = str(file_path)
        summaries.append(payload)

    return summaries


def average(values: list[float]) -> float:
    if not values:
        return 0.0

    return sum(values) / len(values)


def build_check(code: str, passed: bool, value: Any, expected: Any) -> dict[str, Any]:
    return {
        "code": code,
        "status": "PASS" if passed else "FAIL",
        "value": value,
        "expected": expected,
        "blocking": not passed,
    }


def build_testnet_continuous_report(
    *,
    summaries: list[dict[str, Any]] | None = None,
    config: TestnetContinuousConfig | None = None,
) -> TestnetContinuousReport:
    resolved_config = config or load_testnet_continuous_config()
    resolved_summaries = summaries if summaries is not None else load_session_summaries(resolved_config.output_dir)

    sessions_count = len(resolved_summaries)

    metrics_list = [
        summary.get("metrics") or {}
        for summary in resolved_summaries
    ]

    trades_count = sum(int(metrics.get("filled_orders", 0) or 0) for metrics in metrics_list)

    fill_rates = [float(metrics.get("fill_rate", 0) or 0) for metrics in metrics_list]
    rejection_rates = [float(metrics.get("rejection_rate", 0) or 0) for metrics in metrics_list]
    cancel_rates = [float(metrics.get("cancel_rate", 0) or 0) for metrics in metrics_list]
    pnl_values = [float(metrics.get("net_pnl_usd", 0) or 0) for metrics in metrics_list]

    average_fill_rate = average(fill_rates)
    average_rejection_rate = average(rejection_rates)
    average_cancel_rate = average(cancel_rates)
    total_net_pnl = sum(pnl_values)

    checks = [
        build_check("SESSIONS_COUNT_OK", sessions_count >= resolved_config.min_sessions, sessions_count, f">={resolved_config.min_sessions}"),
        build_check("TRADES_COUNT_OK", trades_count >= resolved_config.min_trades, trades_count, f">={resolved_config.min_trades}"),
        build_check("FILL_RATE_OK", average_fill_rate >= resolved_config.min_fill_rate, average_fill_rate, f">={resolved_config.min_fill_rate}"),
        build_check("REJECTION_RATE_OK", average_rejection_rate <= resolved_config.max_rejection_rate, average_rejection_rate, f"<={resolved_config.max_rejection_rate}"),
        build_check("CANCEL_RATE_OK", average_cancel_rate <= resolved_config.max_cancel_rate, average_cancel_rate, f"<={resolved_config.max_cancel_rate}"),
    ]

    passed = all(check["status"] == "PASS" for check in checks)

    return TestnetContinuousReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        sessions_count=sessions_count,
        trades_count=trades_count,
        average_fill_rate=average_fill_rate,
        average_rejection_rate=average_rejection_rate,
        average_cancel_rate=average_cancel_rate,
        total_net_pnl_usd=total_net_pnl,
        checks=checks,
        source_files=[summary.get("_file") for summary in resolved_summaries if summary.get("_file")],
    )


def export_testnet_continuous_report(
    report: TestnetContinuousReport,
    *,
    output_dir: str | Path = "artifacts/testnet",
    name: str = "testnet_continuous_latest",
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