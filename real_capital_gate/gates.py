from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()

__test__ = False


GateStatus = Literal["PASS", "WARN", "FAIL"]
GateDecision = Literal["GO", "HOLD", "NO_GO"]


SENSITIVE_KEYS = {
    "api_key",
    "api_secret",
    "secret",
    "token",
    "password",
    "private_key",
    "signature",
}


PLACEHOLDERS = {
    "COLE_SUA_API_KEY_LIVE_AQUI",
    "COLE_SUA_SECRET_KEY_LIVE_AQUI",
    "SUA_API_KEY_LIVE",
    "SUA_SECRET_KEY_LIVE",
    "YOUR_API_KEY",
    "YOUR_API_SECRET",
    "CHANGE_ME",
    "CHANGEME",
    "***",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return float(value)
    except ValueError:
        return default


def is_placeholder(value: str | None) -> bool:
    if not value:
        return False

    normalized = value.strip().upper()

    return normalized in PLACEHOLDERS or normalized.startswith("COLE_")


def is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()

    return (
        normalized in SENSITIVE_KEYS
        or "api_key" in normalized
        or "api_secret" in normalized
        or "secret" in normalized
        or "signature" in normalized
        or "private_key" in normalized
        or "password" in normalized
        or "token" in normalized
    )


def sanitize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        result: dict[str, Any] = {}

        for key, value in payload.items():
            if is_sensitive_key(str(key)):
                result[key] = "***" if value else value
            else:
                result[key] = sanitize_payload(value)

        return result

    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]

    if isinstance(payload, str) and is_placeholder(payload):
        return "***"

    return payload


def status_decision(passed: bool, warnings: list[str]) -> tuple[GateStatus, GateDecision]:
    if not passed:
        return "FAIL", "NO_GO"

    if warnings:
        return "WARN", "HOLD"

    return "PASS", "GO"


class GateReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    generated_at: datetime = Field(default_factory=utc_now)

    status: GateStatus
    passed: bool
    decision: GateDecision

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LiveCredentialIsolationReport(GateReport):
    source: str = "live_credential_isolation_check"

    live_api_key_present: bool
    live_api_secret_present: bool
    live_key_placeholder: bool
    live_secret_placeholder: bool

    testnet_api_key_present: bool
    testnet_api_secret_present: bool
    live_equals_testnet_key: bool
    live_equals_testnet_secret: bool

    live_rest_base_url: str
    live_endpoint_detected: bool

    live_order_submission_allowed: bool
    live_cancel_orders_allowed: bool


class LiveApiPermissionAuditReport(GateReport):
    source: str = "live_api_permission_audit"

    enable_reading: bool
    enable_futures: bool
    enable_spot_margin: bool
    enable_withdrawals: bool
    enable_internal_transfer: bool
    ip_restricted: bool


class MicroCapitalRiskEnvelopeReport(GateReport):
    source: str = "micro_capital_risk_envelope"

    max_capital_usd: float
    max_order_notional_usd: float
    max_daily_loss_usd: float
    max_session_loss_usd: float
    max_position_qty: float
    max_leverage: float
    max_orders_per_session: int
    require_flat_after_session: bool
    risk_score: int


class HumanApprovalRecordReport(GateReport):
    source: str = "human_approval_record"

    operator_name: str
    approval_text_present: bool
    approval_hash: str

    confirms_testnet_review_passed: bool
    confirms_readonly_live_only: bool
    confirms_no_withdrawal_permission: bool
    confirms_micro_capital_limits: bool
    confirms_kill_switch_ready: bool
    confirms_no_financial_advice: bool


class EmergencyShutdownDrillReport(GateReport):
    source: str = "micro_live_emergency_shutdown_drill"

    cancel_single_order_route_available: bool
    cancel_all_orders_route_available: bool
    live_new_orders_blocked_after_shutdown: bool
    readonly_reconciliation_available: bool
    incident_report_generator_available: bool
    operator_can_execute_shutdown: bool
    drill_mode: str = "NO_LIVE_CALLS"


class MicroLiveGoNoGoReport(GateReport):
    source: str = "micro_live_go_no_go_report"

    credential_isolation_passed: bool
    api_permission_audit_passed: bool
    risk_envelope_passed: bool
    human_approval_passed: bool
    emergency_shutdown_drill_passed: bool

    credential_isolation: dict[str, Any] = Field(default_factory=dict)
    api_permission_audit: dict[str, Any] = Field(default_factory=dict)
    risk_envelope: dict[str, Any] = Field(default_factory=dict)
    human_approval: dict[str, Any] = Field(default_factory=dict)
    emergency_shutdown_drill: dict[str, Any] = Field(default_factory=dict)


def evaluate_live_credential_isolation() -> LiveCredentialIsolationReport:
    live_key = os.getenv("BINANCE_LIVE_API_KEY", "")
    live_secret = os.getenv("BINANCE_LIVE_API_SECRET", "")

    testnet_key = os.getenv("BINANCE_TESTNET_API_KEY", "")
    testnet_secret = os.getenv("BINANCE_TESTNET_API_SECRET", "")

    live_base_url = os.getenv("BINANCE_LIVE_REST_BASE_URL", "https://fapi.binance.com").strip()

    live_submit = env_bool("BINANCE_LIVE_ALLOW_ORDER_SUBMISSION", False)
    live_cancel = env_bool("BINANCE_LIVE_ALLOW_CANCEL_ORDERS", False)

    require_live_credentials = env_bool("REAL_CAPITAL_REQUIRE_LIVE_CREDENTIALS", False)
    require_live_endpoint = env_bool("REAL_CAPITAL_REQUIRE_LIVE_ENDPOINT", True)
    require_testnet_separation = env_bool("REAL_CAPITAL_REQUIRE_TESTNET_SEPARATION", True)
    require_submit_disabled = env_bool("REAL_CAPITAL_REQUIRE_SUBMIT_DISABLED", True)
    require_cancel_disabled = env_bool("REAL_CAPITAL_REQUIRE_CANCEL_DISABLED", True)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    live_key_present = bool(live_key.strip())
    live_secret_present = bool(live_secret.strip())
    live_key_placeholder = is_placeholder(live_key)
    live_secret_placeholder = is_placeholder(live_secret)

    testnet_key_present = bool(testnet_key.strip())
    testnet_secret_present = bool(testnet_secret.strip())

    live_equals_testnet_key = live_key_present and testnet_key_present and live_key.strip() == testnet_key.strip()
    live_equals_testnet_secret = (
        live_secret_present and testnet_secret_present and live_secret.strip() == testnet_secret.strip()
    )

    live_endpoint_detected = "testnet" not in live_base_url.lower() and "demo" not in live_base_url.lower()

    if require_live_credentials and not live_key_present:
        blockers.append("live_api_key_required")

    if require_live_credentials and not live_secret_present:
        blockers.append("live_api_secret_required")

    if live_key_placeholder:
        blockers.append("live_api_key_placeholder_detected")

    if live_secret_placeholder:
        blockers.append("live_api_secret_placeholder_detected")

    if require_testnet_separation and live_equals_testnet_key:
        blockers.append("live_api_key_matches_testnet_key")

    if require_testnet_separation and live_equals_testnet_secret:
        blockers.append("live_api_secret_matches_testnet_secret")

    if require_live_endpoint and not live_endpoint_detected:
        blockers.append("live_endpoint_not_detected")

    if require_submit_disabled and live_submit:
        blockers.append("live_order_submission_must_be_disabled_at_gate")

    if require_cancel_disabled and live_cancel:
        blockers.append("live_cancel_orders_must_be_disabled_at_gate")

    if not live_key_present or not live_secret_present:
        warnings.append("live_credentials_not_configured_yet")

    recommendations.append("Usar chave live separada da chave testnet.")
    recommendations.append("Nunca commitar .env, .env.live, API key ou API secret.")
    recommendations.append("Manter submit/cancel live desligados durante toda a Fase 32.")

    passed = not blockers
    status, decision = status_decision(passed, warnings)

    return LiveCredentialIsolationReport(
        status=status,
        passed=passed,
        decision=decision,
        live_api_key_present=live_key_present,
        live_api_secret_present=live_secret_present,
        live_key_placeholder=live_key_placeholder,
        live_secret_placeholder=live_secret_placeholder,
        testnet_api_key_present=testnet_key_present,
        testnet_api_secret_present=testnet_secret_present,
        live_equals_testnet_key=live_equals_testnet_key,
        live_equals_testnet_secret=live_equals_testnet_secret,
        live_rest_base_url=live_base_url,
        live_endpoint_detected=live_endpoint_detected,
        live_order_submission_allowed=live_submit,
        live_cancel_orders_allowed=live_cancel,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def evaluate_live_api_permission_audit() -> LiveApiPermissionAuditReport:
    enable_reading = env_bool("BINANCE_LIVE_API_ENABLE_READING", False)
    enable_futures = env_bool("BINANCE_LIVE_API_ENABLE_FUTURES", False)
    enable_spot_margin = env_bool("BINANCE_LIVE_API_ENABLE_SPOT_MARGIN", False)
    enable_withdrawals = env_bool("BINANCE_LIVE_API_ENABLE_WITHDRAWALS", False)
    enable_internal_transfer = env_bool("BINANCE_LIVE_API_ENABLE_INTERNAL_TRANSFER", False)
    ip_restricted = env_bool("BINANCE_LIVE_API_IP_RESTRICTED", False)

    require_reading = env_bool("LIVE_API_REQUIRE_READING_ENABLED", True)
    require_futures = env_bool("LIVE_API_REQUIRE_FUTURES_ENABLED", True)
    require_withdrawals_disabled = env_bool("LIVE_API_REQUIRE_WITHDRAWALS_DISABLED", True)
    require_internal_transfer_disabled = env_bool("LIVE_API_REQUIRE_INTERNAL_TRANSFER_DISABLED", True)
    require_ip_restriction = env_bool("LIVE_API_REQUIRE_IP_RESTRICTION", False)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if require_reading and not enable_reading:
        blockers.append("reading_permission_not_declared_enabled")

    if require_futures and not enable_futures:
        blockers.append("futures_permission_not_declared_enabled")

    if require_withdrawals_disabled and enable_withdrawals:
        blockers.append("withdrawals_permission_must_be_disabled")

    if require_internal_transfer_disabled and enable_internal_transfer:
        blockers.append("internal_transfer_permission_must_be_disabled")

    if require_ip_restriction and not ip_restricted:
        blockers.append("ip_restriction_required")

    if not ip_restricted:
        warnings.append("ip_restriction_not_declared")

    if enable_spot_margin:
        warnings.append("spot_margin_permission_enabled_review_needed")

    recommendations.append("Verificar permissões diretamente no painel Binance API Management.")
    recommendations.append("Withdrawal deve permanecer desabilitado para API de robô.")
    recommendations.append("Ativar restrição por IP antes de qualquer operação live, quando possível.")

    passed = not blockers
    status, decision = status_decision(passed, warnings)

    return LiveApiPermissionAuditReport(
        status=status,
        passed=passed,
        decision=decision,
        enable_reading=enable_reading,
        enable_futures=enable_futures,
        enable_spot_margin=enable_spot_margin,
        enable_withdrawals=enable_withdrawals,
        enable_internal_transfer=enable_internal_transfer,
        ip_restricted=ip_restricted,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def evaluate_micro_capital_risk_envelope() -> MicroCapitalRiskEnvelopeReport:
    max_capital_usd = env_float("MICRO_LIVE_MAX_CAPITAL_USD", 25)
    max_order_notional_usd = env_float("MICRO_LIVE_MAX_ORDER_NOTIONAL_USD", 10)
    max_daily_loss_usd = env_float("MICRO_LIVE_MAX_DAILY_LOSS_USD", 5)
    max_session_loss_usd = env_float("MICRO_LIVE_MAX_SESSION_LOSS_USD", 2)
    max_position_qty = env_float("MICRO_LIVE_MAX_POSITION_QTY", 0.001)
    max_leverage = env_float("MICRO_LIVE_MAX_LEVERAGE", 1)
    max_orders_per_session = int(env_float("MICRO_LIVE_MAX_ORDERS_PER_SESSION", 3))
    require_flat_after_session = env_bool("MICRO_LIVE_REQUIRE_FLAT_AFTER_SESSION", True)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if max_capital_usd <= 0:
        blockers.append("max_capital_must_be_positive")

    if max_capital_usd > 100:
        blockers.append("micro_capital_above_safe_limit")

    if max_order_notional_usd <= 0:
        blockers.append("max_order_notional_must_be_positive")

    if max_order_notional_usd > max_capital_usd:
        blockers.append("order_notional_above_total_capital")

    if max_daily_loss_usd <= 0:
        blockers.append("max_daily_loss_must_be_positive")

    if max_daily_loss_usd > max_capital_usd * 0.25:
        blockers.append("daily_loss_limit_too_high")

    if max_session_loss_usd > max_daily_loss_usd:
        blockers.append("session_loss_above_daily_loss")

    if max_leverage > 1:
        warnings.append("leverage_above_one_review_required")

    if max_orders_per_session > 5:
        warnings.append("orders_per_session_above_micro_default")

    if not require_flat_after_session:
        blockers.append("flat_after_session_required_for_micro_live")

    risk_score = 0
    risk_score += 3 if max_capital_usd > 50 else 1
    risk_score += 3 if max_leverage > 1 else 0
    risk_score += 2 if max_orders_per_session > 3 else 0
    risk_score += 3 if max_daily_loss_usd > max_capital_usd * 0.1 else 1

    recommendations.append("Começar com microcapital e sem aumento automático.")
    recommendations.append("Qualquer perda acima do envelope deve acionar HOLD/NO-GO.")
    recommendations.append("Capital real não deve ser escalado por PnL recente.")

    passed = not blockers
    status, decision = status_decision(passed, warnings)

    return MicroCapitalRiskEnvelopeReport(
        status=status,
        passed=passed,
        decision=decision,
        max_capital_usd=max_capital_usd,
        max_order_notional_usd=max_order_notional_usd,
        max_daily_loss_usd=max_daily_loss_usd,
        max_session_loss_usd=max_session_loss_usd,
        max_position_qty=max_position_qty,
        max_leverage=max_leverage,
        max_orders_per_session=max_orders_per_session,
        require_flat_after_session=require_flat_after_session,
        risk_score=risk_score,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def approval_hash(operator_name: str, approval_text: str) -> str:
    return hashlib.sha256(f"{operator_name}|{approval_text}".encode("utf-8")).hexdigest()


def evaluate_human_approval_record() -> HumanApprovalRecordReport:
    operator_name = os.getenv("MICRO_LIVE_OPERATOR_NAME", "")
    approval_text = os.getenv("MICRO_LIVE_APPROVAL_TEXT", "")

    confirms_testnet_review_passed = env_bool("MICRO_LIVE_APPROVE_TESTNET_REVIEW_PASSED", False)
    confirms_readonly_live_only = env_bool("MICRO_LIVE_APPROVE_READONLY_LIVE_ONLY", False)
    confirms_no_withdrawal_permission = env_bool("MICRO_LIVE_APPROVE_NO_WITHDRAWAL_PERMISSION", False)
    confirms_micro_capital_limits = env_bool("MICRO_LIVE_APPROVE_MICRO_CAPITAL_LIMITS", False)
    confirms_kill_switch_ready = env_bool("MICRO_LIVE_APPROVE_KILL_SWITCH_READY", False)
    confirms_no_financial_advice = env_bool("MICRO_LIVE_APPROVE_NO_FINANCIAL_ADVICE", False)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if not operator_name.strip():
        blockers.append("operator_name_required")

    if not approval_text.strip():
        blockers.append("approval_text_required")

    required_flags = {
        "testnet_review_not_confirmed": confirms_testnet_review_passed,
        "readonly_live_only_not_confirmed": confirms_readonly_live_only,
        "no_withdrawal_permission_not_confirmed": confirms_no_withdrawal_permission,
        "micro_capital_limits_not_confirmed": confirms_micro_capital_limits,
        "kill_switch_ready_not_confirmed": confirms_kill_switch_ready,
        "no_financial_advice_not_confirmed": confirms_no_financial_advice,
    }

    for blocker, ok in required_flags.items():
        if not ok:
            blockers.append(blocker)

    recommendations.append("Aprovação humana deve ser explícita antes de qualquer live.")
    recommendations.append("Sem aprovação humana, decisão final permanece NO_GO.")

    passed = not blockers
    status, decision = status_decision(passed, warnings)

    return HumanApprovalRecordReport(
        status=status,
        passed=passed,
        decision=decision,
        operator_name=operator_name,
        approval_text_present=bool(approval_text.strip()),
        approval_hash=approval_hash(operator_name, approval_text),
        confirms_testnet_review_passed=confirms_testnet_review_passed,
        confirms_readonly_live_only=confirms_readonly_live_only,
        confirms_no_withdrawal_permission=confirms_no_withdrawal_permission,
        confirms_micro_capital_limits=confirms_micro_capital_limits,
        confirms_kill_switch_ready=confirms_kill_switch_ready,
        confirms_no_financial_advice=confirms_no_financial_advice,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def evaluate_emergency_shutdown_drill() -> EmergencyShutdownDrillReport:
    cancel_single = env_bool("EMERGENCY_DRILL_CANCEL_SINGLE_AVAILABLE", True)
    cancel_all = env_bool("EMERGENCY_DRILL_CANCEL_ALL_AVAILABLE", True)
    new_orders_blocked = env_bool("EMERGENCY_DRILL_NEW_ORDERS_BLOCKED", True)
    readonly_reconciliation = env_bool("EMERGENCY_DRILL_READONLY_RECONCILIATION_AVAILABLE", True)
    incident_report = env_bool("EMERGENCY_DRILL_INCIDENT_REPORT_AVAILABLE", True)
    operator_can_execute = env_bool("EMERGENCY_DRILL_OPERATOR_CAN_EXECUTE", True)

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    checks = {
        "cancel_single_order_route_unavailable": cancel_single,
        "cancel_all_orders_route_unavailable": cancel_all,
        "live_new_orders_not_blocked_after_shutdown": new_orders_blocked,
        "readonly_reconciliation_unavailable": readonly_reconciliation,
        "incident_report_generator_unavailable": incident_report,
        "operator_cannot_execute_shutdown": operator_can_execute,
    }

    for blocker, ok in checks.items():
        if not ok:
            blockers.append(blocker)

    recommendations.append("Kill switch real deve cancelar ordens abertas e bloquear novas ordens.")
    recommendations.append("Depois de qualquer shutdown, rodar read-only snapshot e incident report.")
    recommendations.append("Este drill não chama endpoint live; é validação estrutural.")

    passed = not blockers
    status, decision = status_decision(passed, warnings)

    return EmergencyShutdownDrillReport(
        status=status,
        passed=passed,
        decision=decision,
        cancel_single_order_route_available=cancel_single,
        cancel_all_orders_route_available=cancel_all,
        live_new_orders_blocked_after_shutdown=new_orders_blocked,
        readonly_reconciliation_available=readonly_reconciliation,
        incident_report_generator_available=incident_report,
        operator_can_execute_shutdown=operator_can_execute,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def build_micro_live_go_no_go_report() -> MicroLiveGoNoGoReport:
    credential = evaluate_live_credential_isolation()
    permission = evaluate_live_api_permission_audit()
    risk = evaluate_micro_capital_risk_envelope()
    approval = evaluate_human_approval_record()
    drill = evaluate_emergency_shutdown_drill()

    components = {
        "credential_isolation": credential,
        "api_permission_audit": permission,
        "risk_envelope": risk,
        "human_approval": approval,
        "emergency_shutdown_drill": drill,
    }

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    for name, report in components.items():
        if not report.passed:
            blockers.append(f"{name}_not_passed")

        for blocker in report.blockers:
            blockers.append(f"{name}:{blocker}")

        for warning in report.warnings:
            warnings.append(f"{name}:{warning}")

        for recommendation in report.recommendations:
            recommendations.append(f"{name}:{recommendation}")

    recommendations.append("GO nesta fase significa pronto para Live Read-Only, não para enviar ordem real.")
    recommendations.append("Não ligar submit/cancel live nesta fase.")
    recommendations.append("Se qualquer env ou artifact mudar, reexecutar toda a Fase 32.")

    passed = not blockers
    status, decision = status_decision(passed, warnings)

    return MicroLiveGoNoGoReport(
        status=status,
        passed=passed,
        decision=decision,
        credential_isolation_passed=credential.passed,
        api_permission_audit_passed=permission.passed,
        risk_envelope_passed=risk.passed,
        human_approval_passed=approval.passed,
        emergency_shutdown_drill_passed=drill.passed,
        credential_isolation=sanitize_payload(credential.model_dump(mode="json")),
        api_permission_audit=sanitize_payload(permission.model_dump(mode="json")),
        risk_envelope=sanitize_payload(risk.model_dump(mode="json")),
        human_approval=sanitize_payload(approval.model_dump(mode="json")),
        emergency_shutdown_drill=sanitize_payload(drill.model_dump(mode="json")),
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def export_gate_json(
    report: GateReport | dict[str, Any],
    *,
    output_dir: str | Path = "artifacts/real_capital_gate",
    name: str,
) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"

    data = report.model_dump(mode="json") if hasattr(report, "model_dump") else report
    data = sanitize_payload(data)

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path