from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live.common import env_bool, env_str, export_json


EmergencyDrillStatus = Literal["PASS", "WARN", "FAIL"]


class EmergencyShutdownDrillConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/micro_live")

    emergency_stop_file: Path = Path("artifacts/micro_live/emergency_stop.flag")
    require_emergency_stop_drill: bool = True
    require_kill_switch_writable: bool = True


class EmergencyShutdownDrillReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_live_emergency_shutdown_drill"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: EmergencyDrillStatus
    passed: bool

    emergency_stop_file: str
    directory_writable: bool
    stop_file_created: bool
    stop_file_removed: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    config: dict[str, Any]


def load_emergency_shutdown_drill_config() -> EmergencyShutdownDrillConfig:
    return EmergencyShutdownDrillConfig(
        output_dir=Path(os.getenv("MICRO_LIVE_OUTPUT_DIR", "artifacts/micro_live")),
        emergency_stop_file=Path(env_str("MICRO_LIVE_EMERGENCY_STOP_FILE", "artifacts/micro_live/emergency_stop.flag")),
        require_emergency_stop_drill=env_bool("MICRO_LIVE_REQUIRE_EMERGENCY_STOP_DRILL", True),
        require_kill_switch_writable=env_bool("MICRO_LIVE_REQUIRE_KILL_SWITCH_WRITABLE", True),
    )


def run_emergency_shutdown_drill(
    *,
    config: EmergencyShutdownDrillConfig | None = None,
) -> EmergencyShutdownDrillReport:
    resolved = config or load_emergency_shutdown_drill_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    stop_file = resolved.emergency_stop_file
    stop_dir = stop_file.parent

    directory_writable = False
    stop_file_created = False
    stop_file_removed = False

    try:
        stop_dir.mkdir(parents=True, exist_ok=True)
        probe = stop_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        directory_writable = True
    except OSError:
        directory_writable = False

    if resolved.require_kill_switch_writable and not directory_writable:
        blockers.append("emergency_stop_directory_not_writable")

    if directory_writable and resolved.require_emergency_stop_drill:
        try:
            stop_file.write_text("EMERGENCY_STOP_DRILL", encoding="utf-8")
            stop_file_created = stop_file.exists()
            stop_file.unlink(missing_ok=True)
            stop_file_removed = not stop_file.exists()
        except OSError:
            blockers.append("emergency_stop_file_drill_failed")

    if resolved.require_emergency_stop_drill and not stop_file_created:
        blockers.append("emergency_stop_file_not_created")

    if resolved.require_emergency_stop_drill and not stop_file_removed:
        blockers.append("emergency_stop_file_not_removed_after_drill")

    recommendations.append("Emergency stop precisa ser testado antes de qualquer micro-live.")
    recommendations.append("O operador deve saber acionar kill switch manualmente.")

    passed = not blockers

    return EmergencyShutdownDrillReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        emergency_stop_file=str(stop_file),
        directory_writable=directory_writable,
        stop_file_created=stop_file_created,
        stop_file_removed=stop_file_removed,
        blockers=blockers,
        warnings=warnings,
        recommendations=sorted(set(recommendations)),
        config=resolved.model_dump(mode="json"),
    )


def export_emergency_shutdown_drill_report(
    report: EmergencyShutdownDrillReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "micro_live_emergency_shutdown_drill",
) -> Path:
    resolved = load_emergency_shutdown_drill_config()
    return export_json(report, output_dir=output_dir or resolved.output_dir, name=name)