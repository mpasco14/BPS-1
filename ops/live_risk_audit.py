from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from ops.live_session_recorder import LiveRecordedEvent, load_live_session_events


load_dotenv()


RiskAuditSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
RiskAuditStatus = Literal["PASS", "WARN", "FAIL"]


class LiveRiskAuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/live")

    max_margin_usd: float = 20.0
    max_notional_usd: float = 600.0
    max_leverage: int = 30
    max_daily_loss_usd: float = 5.0
    max_open_positions: int = 1

    require_preflight: bool = True
    require_live_guard: bool = True
    require_no_trade_pass: bool = True
    block_on_critical: bool = True


class LiveRiskAuditFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    severity: RiskAuditSeverity
    message: str

    event_id: str | None = None
    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class LiveRiskAuditReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "live_risk_audit"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_name: str
    status: RiskAuditStatus
    passed: bool

    events_count: int
    findings_count: int
    critical_findings_count: int
    blocking_findings_count: int

    max_margin_seen_usd: float = 0.0
    max_notional_seen_usd: float = 0.0
    max_leverage_seen: int | None = None
    realized_daily_pnl_usd: float = 0.0

    findings: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


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


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_live_risk_audit_config() -> LiveRiskAuditConfig:
    return LiveRiskAuditConfig(
        output_dir=Path(os.getenv("LIVE_RISK_AUDIT_OUTPUT_DIR", "artifacts/live")),
        max_margin_usd=env_float("LIVE_RISK_AUDIT_MAX_MARGIN_USD", 20),
        max_notional_usd=env_float("LIVE_RISK_AUDIT_MAX_NOTIONAL_USD", 600),
        max_leverage=env_int("LIVE_RISK_AUDIT_MAX_LEVERAGE", 30),
        max_daily_loss_usd=env_float("LIVE_RISK_AUDIT_MAX_DAILY_LOSS_USD", 5),
        max_open_positions=env_int("LIVE_RISK_AUDIT_MAX_OPEN_POSITIONS", 1),
        require_preflight=env_bool("LIVE_RISK_AUDIT_REQUIRE_PREFLIGHT", True),
        require_live_guard=env_bool("LIVE_RISK_AUDIT_REQUIRE_LIVE_GUARD", True),
        require_no_trade_pass=env_bool("LIVE_RISK_AUDIT_REQUIRE_NO_TRADE_PASS", True),
        block_on_critical=env_bool("LIVE_RISK_AUDIT_BLOCK_ON_CRITICAL", True),
    )


def finding(
    *,
    code: str,
    severity: RiskAuditSeverity,
    message: str,
    event_id: str | None = None,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> LiveRiskAuditFinding:
    return LiveRiskAuditFinding(
        code=code,
        severity=severity,
        message=message,
        event_id=event_id,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def audit_event(
    event: LiveRecordedEvent,
    *,
    config: LiveRiskAuditConfig,
) -> list[LiveRiskAuditFinding]:
    findings: list[LiveRiskAuditFinding] = []

    if event.margin_usd > config.max_margin_usd:
        findings.append(
            finding(
                code="margin_above_limit",
                severity="CRITICAL",
                message="Margem da ordem/evento acima do limite permitido.",
                event_id=event.event_id,
                value=event.margin_usd,
                expected=f"<={config.max_margin_usd}",
                blocking=True,
            )
        )

    if event.notional_usd > config.max_notional_usd:
        findings.append(
            finding(
                code="notional_above_limit",
                severity="CRITICAL",
                message="Notional da ordem/evento acima do limite permitido.",
                event_id=event.event_id,
                value=event.notional_usd,
                expected=f"<={config.max_notional_usd}",
                blocking=True,
            )
        )

    if event.leverage is not None and event.leverage > config.max_leverage:
        findings.append(
            finding(
                code="leverage_above_limit",
                severity="CRITICAL",
                message="Leverage acima do limite permitido.",
                event_id=event.event_id,
                value=event.leverage,
                expected=f"<={config.max_leverage}",
                blocking=True,
            )
        )

    if config.require_preflight and event.event_type in {"PLANNED", "SUBMITTED"} and event.preflight_passed is not True:
        findings.append(
            finding(
                code="preflight_not_passed",
                severity="CRITICAL",
                message="Evento planejado/submetido sem preflight aprovado.",
                event_id=event.event_id,
                value=event.preflight_passed,
                expected=True,
                blocking=True,
            )
        )

    if config.require_live_guard and event.event_type in {"PLANNED", "SUBMITTED"} and event.live_guard_passed is not True:
        findings.append(
            finding(
                code="live_guard_not_passed",
                severity="CRITICAL",
                message="Evento planejado/submetido sem live guard aprovado.",
                event_id=event.event_id,
                value=event.live_guard_passed,
                expected=True,
                blocking=True,
            )
        )

    if config.require_no_trade_pass and event.event_type in {"PLANNED", "SUBMITTED"} and event.no_trade_passed is not True:
        findings.append(
            finding(
                code="no_trade_not_passed",
                severity="HIGH",
                message="Evento planejado/submetido sem aprovação do No-Trade Engine.",
                event_id=event.event_id,
                value=event.no_trade_passed,
                expected=True,
                blocking=True,
            )
        )

    if event.risk_state_status and event.risk_state_status != "OK":
        findings.append(
            finding(
                code="risk_state_not_ok",
                severity="HIGH",
                message="Evento ocorreu com risk_state diferente de OK.",
                event_id=event.event_id,
                value=event.risk_state_status,
                expected="OK",
                blocking=True,
            )
        )

    for blocker in event.risk_blockers:
        findings.append(
            finding(
                code=f"risk_blocker:{blocker}",
                severity="HIGH",
                message="Evento contém risk blocker.",
                event_id=event.event_id,
                value=blocker,
                blocking=True,
            )
        )

    for blocker in event.guard_blockers:
        findings.append(
            finding(
                code=f"guard_blocker:{blocker}",
                severity="HIGH",
                message="Evento contém live guard blocker.",
                event_id=event.event_id,
                value=blocker,
                blocking=True,
            )
        )

    for blocker in event.no_trade_blockers:
        findings.append(
            finding(
                code=f"no_trade_blocker:{blocker}",
                severity="MEDIUM",
                message="Evento contém no-trade blocker.",
                event_id=event.event_id,
                value=blocker,
                blocking=False,
            )
        )

    return findings


def build_live_risk_audit_report(
    *,
    events: list[LiveRecordedEvent | dict[str, Any]] | None = None,
    events_path: str | Path | None = None,
    session_name: str = "live_micro_session",
    config: LiveRiskAuditConfig | None = None,
) -> LiveRiskAuditReport:
    resolved_config = config or load_live_risk_audit_config()

    if events is None:
        parsed_events = load_live_session_events(events_path, session_name=session_name)
    else:
        parsed_events = [
            item if isinstance(item, LiveRecordedEvent) else LiveRecordedEvent.model_validate(item)
            for item in events
        ]
        parsed_events = [item for item in parsed_events if item.session_name == session_name]

    findings: list[LiveRiskAuditFinding] = []

    for event in parsed_events:
        findings.extend(audit_event(event, config=resolved_config))

    realized_daily_pnl = sum(item.net_pnl_usd for item in parsed_events)

    if realized_daily_pnl <= -abs(resolved_config.max_daily_loss_usd):
        findings.append(
            finding(
                code="daily_loss_limit_reached",
                severity="CRITICAL",
                message="Perda diária realizada atingiu ou passou o limite.",
                value=realized_daily_pnl,
                expected=f">-{resolved_config.max_daily_loss_usd}",
                blocking=True,
            )
        )

    leverage_values = [item.leverage for item in parsed_events if item.leverage is not None]

    critical_count = sum(1 for item in findings if item.severity == "CRITICAL")
    blocking_count = sum(1 for item in findings if item.blocking)

    passed = blocking_count == 0

    if not passed:
        status: RiskAuditStatus = "FAIL"
    elif findings:
        status = "WARN"
    else:
        status = "PASS"

    return LiveRiskAuditReport(
        session_name=session_name,
        status=status,
        passed=passed,
        events_count=len(parsed_events),
        findings_count=len(findings),
        critical_findings_count=critical_count,
        blocking_findings_count=blocking_count,
        max_margin_seen_usd=max([item.margin_usd for item in parsed_events], default=0.0),
        max_notional_seen_usd=max([item.notional_usd for item in parsed_events], default=0.0),
        max_leverage_seen=max(leverage_values) if leverage_values else None,
        realized_daily_pnl_usd=round(realized_daily_pnl, 8),
        findings=[item.model_dump(mode="json") for item in findings],
        config=resolved_config.model_dump(mode="json"),
    )


def export_live_risk_audit_report(
    report: LiveRiskAuditReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "live_risk_audit_latest",
) -> Path:
    config = load_live_risk_audit_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path