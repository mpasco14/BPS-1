from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


E2EScenarioKind = Literal[
    "paper_trading",
    "testnet_dry_run",
    "failure",
    "kill_switch",
]

E2EScenarioStatus = Literal[
    "PASS",
    "WARN",
    "FAIL",
    "EXPECTED_BLOCKED",
]


class E2EConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/e2e")
    session_name: str = "e2e_local_session"
    default_symbol: str = "BTCUSDT"
    default_timeframe: str = "5m"
    default_dry_run: bool = True


class E2EScenarioReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "e2e_scenario_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    scenario_id: str = Field(default_factory=lambda: f"e2e_{uuid4().hex}")
    scenario_name: str
    scenario_kind: E2EScenarioKind

    status: E2EScenarioStatus
    passed: bool
    expected_blocked: bool = False

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    runtime_context: dict[str, Any] | None = None
    system_state: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None

    components: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class E2EFullSystemReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "e2e_full_system_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: E2EScenarioStatus
    passed: bool

    scenarios_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    expected_blocked_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_e2e_config() -> E2EConfig:
    return E2EConfig(
        output_dir=Path(os.getenv("E2E_OUTPUT_DIR", "artifacts/e2e")),
        session_name=os.getenv("E2E_SESSION_NAME", "e2e_local_session"),
        default_symbol=os.getenv("E2E_DEFAULT_SYMBOL", "BTCUSDT"),
        default_timeframe=os.getenv("E2E_DEFAULT_TIMEFRAME", "5m"),
        default_dry_run=env_bool("E2E_DEFAULT_DRY_RUN", True),
    )


def scenario_status_from_result(
    *,
    passed: bool,
    warnings: list[str] | None = None,
    expected_blocked: bool = False,
) -> E2EScenarioStatus:
    if expected_blocked and passed:
        return "EXPECTED_BLOCKED"

    if not passed:
        return "FAIL"

    if warnings:
        return "WARN"

    return "PASS"


def export_e2e_scenario_report(
    report: E2EScenarioReport,
    *,
    output_dir: str | Path | None = None,
    name: str | None = None,
) -> Path:
    config = load_e2e_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = (name or report.scenario_name).replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path


def export_e2e_full_system_report(
    report: E2EFullSystemReport,
    *,
    path: str | Path | None = None,
) -> Path:
    output_path = Path(path or os.getenv("E2E_FULL_REPORT_FILE", "artifacts/e2e/e2e_full_system_report.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path