from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


SystemSeverity = Literal["INFO", "WARNING", "HIGH", "CRITICAL"]

SystemErrorCode = Literal[
    "CONFIG_ERROR",
    "DATA_QUALITY_FAILURE",
    "RISK_BLOCK",
    "NO_TRADE_BLOCK",
    "SECURITY_BLOCK",
    "INFRA_FAILURE",
    "MODEL_INVALID",
    "MODEL_DRIFT",
    "PORTFOLIO_RISK",
    "EXCHANGE_ERROR",
    "EXECUTION_CONTRACT_FAILURE",
    "OPERATOR_BLOCK",
    "SAFE_MODE",
    "KILL_SWITCH",
    "STATE_TRANSITION_BLOCK",
    "RECONCILIATION_FAILURE",
    "UNKNOWN_CRITICAL",
]


class SystemBlocker(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: SystemErrorCode
    severity: SystemSeverity
    source: str
    message: str

    blocking: bool = True

    detail: str | None = None
    remediation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemBlockerReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "unified_error_blocker_taxonomy"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    blockers_count: int
    critical_count: int
    high_count: int
    warning_count: int
    info_count: int

    blockers: list[dict[str, Any]] = Field(default_factory=list)
    blocking_codes: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


def build_system_blocker(
    *,
    code: SystemErrorCode,
    severity: SystemSeverity,
    source: str,
    message: str,
    blocking: bool | None = None,
    detail: str | None = None,
    remediation: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SystemBlocker:
    resolved_blocking = blocking if blocking is not None else severity in {"HIGH", "CRITICAL"}

    return SystemBlocker(
        code=code,
        severity=severity,
        source=source,
        message=message,
        blocking=resolved_blocking,
        detail=detail,
        remediation=remediation,
        metadata=metadata or {},
    )


def blocker_from_string(
    *,
    code: SystemErrorCode,
    source: str,
    text: str,
    severity: SystemSeverity = "HIGH",
) -> SystemBlocker:
    return build_system_blocker(
        code=code,
        severity=severity,
        source=source,
        message=text,
        remediation=default_remediation_for_code(code),
    )


def default_remediation_for_code(code: SystemErrorCode) -> str:
    mapping: dict[str, str] = {
        "CONFIG_ERROR": "Validar runtime config e bloquear live até corrigir.",
        "DATA_QUALITY_FAILURE": "Bloquear sinal e regenerar features/dados.",
        "RISK_BLOCK": "Não enviar ordem; revisar sizing, drawdown e exposição.",
        "NO_TRADE_BLOCK": "Manter sistema em observação sem abrir nova posição.",
        "SECURITY_BLOCK": "Bloquear operação e revisar secrets, permissões e políticas.",
        "INFRA_FAILURE": "Ativar degradação segura e verificar dependências.",
        "MODEL_INVALID": "Bloquear sinal e usar fallback/watch mode.",
        "MODEL_DRIFT": "Reduzir risco e revisar calibração/drift.",
        "PORTFOLIO_RISK": "Reduzir exposição ou bloquear novas entradas.",
        "EXCHANGE_ERROR": "Pausar execução e reconciliar estado com exchange.",
        "EXECUTION_CONTRACT_FAILURE": "Não enviar ordem; corrigir contrato de execução.",
        "OPERATOR_BLOCK": "Exigir aprovação ou ação manual válida.",
        "SAFE_MODE": "Permitir apenas reduce-only até revisão.",
        "KILL_SWITCH": "Cancelar ordens, bloquear novas entradas e gerar incidente.",
        "STATE_TRANSITION_BLOCK": "Não avançar estado sem evidências obrigatórias.",
        "RECONCILIATION_FAILURE": "Não operar até posição local e exchange baterem.",
        "UNKNOWN_CRITICAL": "Pausar operação e abrir investigação manual.",
    }

    return mapping.get(code, "Revisar manualmente antes de continuar.")


def aggregate_system_blockers(
    *,
    blockers: list[SystemBlocker | dict[str, Any] | str],
    default_code: SystemErrorCode = "UNKNOWN_CRITICAL",
    default_source: str = "system",
) -> SystemBlockerReport:
    parsed: list[SystemBlocker] = []

    for item in blockers:
        if isinstance(item, SystemBlocker):
            parsed.append(item)
        elif isinstance(item, str):
            parsed.append(
                blocker_from_string(
                    code=default_code,
                    source=default_source,
                    text=item,
                    severity="CRITICAL",
                )
            )
        else:
            parsed.append(SystemBlocker.model_validate(item))

    critical = sum(1 for item in parsed if item.severity == "CRITICAL")
    high = sum(1 for item in parsed if item.severity == "HIGH")
    warning = sum(1 for item in parsed if item.severity == "WARNING")
    info = sum(1 for item in parsed if item.severity == "INFO")

    blocking_items = [item for item in parsed if item.blocking]
    passed = not blocking_items

    recommendations = sorted(
        {
            item.remediation
            for item in parsed
            if item.remediation
        }
    )

    return SystemBlockerReport(
        passed=passed,
        status="PASS" if passed and not parsed else "WARN" if passed else "FAIL",
        blockers_count=len(parsed),
        critical_count=critical,
        high_count=high,
        warning_count=warning,
        info_count=info,
        blockers=[item.model_dump(mode="json") for item in parsed],
        blocking_codes=sorted({item.code for item in blocking_items}),
        recommendations=recommendations,
    )


def export_system_blocker_report(
    report: SystemBlockerReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "system_blockers_latest",
) -> Path:
    path = Path(output_dir or os.getenv("ERROR_TAXONOMY_OUTPUT_DIR", "artifacts/system_integration"))
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path