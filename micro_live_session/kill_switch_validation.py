from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from micro_live_session.session_models import (
    MicroLiveSessionConfig,
    export_micro_live_session_json,
    load_micro_live_session_config,
)


KillSwitchStatus = Literal["PASS", "WARN", "FAIL"]


class MicroLiveKillSwitchValidationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_live_stop_kill_switch_validation"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: KillSwitchStatus
    passed: bool

    emergency_stop_file: str
    directory_writable: bool
    kill_switch_file_created: bool
    kill_switch_file_removed: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    config: dict[str, Any]


def validate_micro_live_kill_switch(
    *,
    config: MicroLiveSessionConfig | None = None,
) -> MicroLiveKillSwitchValidationReport:
    resolved = config or load_micro_live_session_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    stop_file = resolved.emergency_stop_file
    stop_dir = stop_file.parent

    directory_writable = False
    created = False
    removed = False

    try:
        stop_dir.mkdir(parents=True, exist_ok=True)
        probe = stop_dir / ".micro_live_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        directory_writable = True
    except OSError:
        directory_writable = False

    if not directory_writable:
        blockers.append("kill_switch_directory_not_writable")

    if directory_writable:
        try:
            stop_file.write_text("MICRO_LIVE_STOP_TEST", encoding="utf-8")
            created = stop_file.exists()
            stop_file.unlink(missing_ok=True)
            removed = not stop_file.exists()
        except OSError:
            blockers.append("kill_switch_file_test_failed")

    if resolved.require_kill_switch and not created:
        blockers.append("kill_switch_file_not_created")

    if resolved.require_kill_switch and not removed:
        blockers.append("kill_switch_file_not_removed")

    recommendations.append("Kill switch deve estar testado imediatamente antes da sessão.")
    recommendations.append("Se stop file persistir, o sistema deve bloquear novas ordens.")

    passed = not blockers

    return MicroLiveKillSwitchValidationReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        emergency_stop_file=str(stop_file),
        directory_writable=directory_writable,
        kill_switch_file_created=created,
        kill_switch_file_removed=removed,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        config=resolved.model_dump(mode="json"),
    )


def export_micro_live_kill_switch_validation_report(
    report: MicroLiveKillSwitchValidationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "micro_live_kill_switch_validation",
) -> Path:
    return export_micro_live_session_json(report, output_dir=output_dir, name=name)