from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()

__test__ = False

Status = Literal["PASS", "WARN", "FAIL"]
Decision = Literal["GO", "HOLD", "NO_GO"]


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


def sanitize_payload(payload: Any) -> Any:
    sensitive = {"api_key", "api_secret", "secret", "signature", "token", "password", "private_key"}

    if isinstance(payload, dict):
        clean = {}
        for key, value in payload.items():
            k = str(key).lower()
            if any(item in k for item in sensitive):
                clean[key] = "***" if value else value
            else:
                clean[key] = sanitize_payload(value)
        return clean

    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]

    if isinstance(payload, str) and "signature=" in payload:
        return payload.split("signature=")[0] + "signature=***"

    return payload


def final_status(passed: bool, warnings: list[str]) -> tuple[Status, Decision]:
    if not passed:
        return "FAIL", "NO_GO"
    if warnings:
        return "WARN", "HOLD"
    return "PASS", "GO"


class MicroLiveConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/micro_live")
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    quantity: float = 0.001
    price: float = 60000.0
    recv_window: int = 5000
    timeout_seconds: int = 10

    rest_base_url: str = "https://fapi.binance.com"
    api_key: str = ""
    api_secret: str = ""

    phase32_report_path: Path = Path("artifacts/real_capital_gate/micro_live_preparation_gate_go_no_go.json")
    readonly_report_path: Path = Path("artifacts/micro_live/first_micro_live_readonly.json")
    dry_run_report_path: Path = Path("artifacts/micro_live/first_micro_live_dry_run_signal.json")

    allow_real_order_submission: bool = False
    allow_real_cancel: bool = False
    allow_kill_switch: bool = False
    confirmation_phrase: str = ""

    max_order_notional_usd: float = 10.0
    require_phase32_passed: bool = True
    require_readonly_passed: bool = True
    require_dry_run_passed: bool = True
    require_no_live_flags_during_readonly: bool = True


class SignedResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "micro_live_signed_client"
    generated_at: datetime = Field(default_factory=utc_now)

    status: str
    ok: bool
    method: str
    path: str
    url: str | None = None
    http_status: int | None = None
    data: Any = None
    error_message: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class GateReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    generated_at: datetime = Field(default_factory=utc_now)

    status: Status
    passed: bool
    decision: Decision

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MicroLiveReadOnlyReport(GateReport):
    source: str = "first_micro_live_readonly_check"

    simulated: bool = False
    final_flat: bool
    open_orders_count: int
    positions_count: int
    wallet_balance: float
    available_balance: float


class MicroLiveDryRunSignalReport(GateReport):
    source: str = "first_micro_live_dry_run_signal"

    symbol: str
    side: str
    quantity: float
    price: float
    notional_usd: float

    risk_passed: bool
    execution_contract_valid: bool
    submitted: bool = False


class MicroLiveSmallOrderReport(GateReport):
    source: str = "first_micro_live_small_order"

    symbol: str
    side: str
    quantity: float
    price: float

    test_order_passed: bool
    submitted: bool
    order_id: int | None = None
    client_order_id: str | None = None
    cancel_attempted: bool = False
    cancel_passed: bool = False
    final_flat: bool = False
    fill_detected: bool = False
    rejection_detected: bool = False


class LiveKillSwitchReport(GateReport):
    source: str = "live_stop_kill_switch_validation"

    symbol: str
    kill_switch_allowed: bool
    cancel_all_attempted: bool = False
    cancel_all_passed: bool = False
    open_orders_after: int | None = None


class MicroLiveSessionReport(GateReport):
    source: str = "micro_live_session_report"

    readonly_passed: bool
    dry_run_passed: bool
    small_order_passed: bool
    kill_switch_passed: bool

    final_flat: bool
    open_orders_count: int


def load_config() -> MicroLiveConfig:
    return MicroLiveConfig(
        output_dir=Path(os.getenv("MICRO_LIVE_OUTPUT_DIR", "artifacts/micro_live")),
        symbol=os.getenv("MICRO_LIVE_SYMBOL", "BTCUSDT"),
        side=os.getenv("MICRO_LIVE_SIDE", "BUY"),
        quantity=env_float("MICRO_LIVE_QUANTITY", 0.001),
        price=env_float("MICRO_LIVE_PRICE", 60000.0),
        rest_base_url=os.getenv("BINANCE_LIVE_REST_BASE_URL", "https://fapi.binance.com"),
        api_key=os.getenv("BINANCE_LIVE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_LIVE_API_SECRET", ""),
        allow_real_order_submission=env_bool("MICRO_LIVE_ALLOW_REAL_ORDER_SUBMISSION", False),
        allow_real_cancel=env_bool("MICRO_LIVE_ALLOW_REAL_CANCEL", False),
        allow_kill_switch=env_bool("MICRO_LIVE_ALLOW_KILL_SWITCH", False),
        confirmation_phrase=os.getenv("MICRO_LIVE_CONFIRM_PHRASE", ""),
        max_order_notional_usd=env_float("MICRO_LIVE_MAX_ORDER_NOTIONAL_USD", 10.0),
        require_phase32_passed=env_bool("MICRO_LIVE_REQUIRE_PHASE32_PASSED", True),
        require_readonly_passed=env_bool("MICRO_LIVE_REQUIRE_READONLY_PASSED", True),
        require_dry_run_passed=env_bool("MICRO_LIVE_REQUIRE_DRY_RUN_PASSED", True),
    )


def export_json(report: BaseModel | dict[str, Any], *, output_dir: str | Path, name: str) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    output_path = path / f"{name}.json"

    data = report.model_dump(mode="json") if hasattr(report, "model_dump") else report
    data = sanitize_payload(data)

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def load_json(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


class MicroLiveSignedClient:
    def __init__(self, config: MicroLiveConfig):
        self.config = config

    def sanitized_config(self) -> dict[str, Any]:
        return sanitize_payload(self.config.model_dump(mode="json"))

    def _sign(self, params: dict[str, Any]) -> str:
        query = urlencode(params, doseq=True)
        return hmac.new(self.config.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()

    def signed_request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> SignedResponse:
        resolved = dict(params or {})
        resolved["recvWindow"] = self.config.recv_window
        resolved["timestamp"] = int(time.time() * 1000)

        query_without_signature = urlencode(resolved, doseq=True)
        resolved["signature"] = self._sign(resolved)

        url = f"{self.config.rest_base_url.rstrip('/')}{path}?{urlencode(resolved, doseq=True)}"

        headers = {"X-MBX-APIKEY": self.config.api_key}

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )

            try:
                data = response.json()
            except ValueError:
                data = response.text

            return SignedResponse(
                status="OK" if response.ok else "ERROR",
                ok=response.ok,
                method=method.upper(),
                path=path,
                url=f"{self.config.rest_base_url.rstrip('/')}{path}?{query_without_signature}&signature=***",
                http_status=response.status_code,
                data=data,
                error_message=None if response.ok else str(data),
                config=self.sanitized_config(),
            )

        except requests.RequestException as exc:
            return SignedResponse(
                status="EXCEPTION",
                ok=False,
                method=method.upper(),
                path=path,
                url=f"{self.config.rest_base_url.rstrip('/')}{path}?signature=***",
                error_message=str(exc),
                config=self.sanitized_config(),
            )


def validate_live_config(config: MicroLiveConfig) -> list[str]:
    blockers: list[str] = []

    if not config.api_key.strip():
        blockers.append("live_api_key_required")

    if not config.api_secret.strip():
        blockers.append("live_api_secret_required")

    if "testnet" in config.rest_base_url.lower() or "demo" in config.rest_base_url.lower():
        blockers.append("live_endpoint_expected_not_testnet")

    if not config.rest_base_url.startswith("https://"):
        blockers.append("https_live_endpoint_required")

    return blockers


def validate_phase32(config: MicroLiveConfig) -> list[str]:
    if not config.require_phase32_passed:
        return []

    report = load_json(config.phase32_report_path)

    if not report:
        return ["phase32_go_no_go_report_missing"]

    if report.get("passed") is not True:
        return ["phase32_go_no_go_not_passed"]

    if report.get("decision") not in {"GO", "HOLD"}:
        return ["phase32_decision_not_acceptable"]

    return []


def run_readonly_check(config: MicroLiveConfig | None = None) -> MicroLiveReadOnlyReport:
    resolved = config or load_config()
    blockers = validate_live_config(resolved) + validate_phase32(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []

    if resolved.require_no_live_flags_during_readonly:
        if env_bool("MICRO_LIVE_ALLOW_REAL_ORDER_SUBMISSION", False):
            blockers.append("real_order_submission_must_be_disabled_for_readonly")
        if env_bool("MICRO_LIVE_ALLOW_REAL_CANCEL", False):
            blockers.append("real_cancel_must_be_disabled_for_readonly")

    wallet_balance = 0.0
    available_balance = 0.0
    positions_count = 0
    open_orders_count = 0
    final_flat = False

    if not blockers:
        client = MicroLiveSignedClient(resolved)

        account = client.signed_request(method="GET", path="/fapi/v2/account")
        open_orders = client.signed_request(method="GET", path="/fapi/v1/openOrders", params={"symbol": resolved.symbol})

        if not account.ok:
            blockers.append("live_account_request_failed")

        if not open_orders.ok:
            blockers.append("live_open_orders_request_failed")

        if account.ok:
            data = account.data or {}
            wallet_balance = float(data.get("totalWalletBalance", 0) or 0)
            available_balance = float(data.get("availableBalance", 0) or 0)
            positions = data.get("positions", []) or []
            relevant = [p for p in positions if str(p.get("symbol", "")).upper() == resolved.symbol.upper()]
            positions_count = len(relevant)
            final_flat = all(abs(float(p.get("positionAmt", 0) or 0)) <= 1e-12 for p in relevant)

        if open_orders.ok:
            open_orders_count = len(open_orders.data or [])

        if open_orders_count > 0:
            blockers.append("live_open_orders_detected")

        if not final_flat:
            blockers.append("live_position_not_flat")

    recommendations.append("Read-only live não deve permitir submit/cancel.")
    recommendations.append("Se houver ordem aberta ou posição não flat, parar e reconciliar manualmente.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return MicroLiveReadOnlyReport(
        status=status,
        passed=passed,
        decision=decision,
        final_flat=final_flat,
        open_orders_count=open_orders_count,
        positions_count=positions_count,
        wallet_balance=wallet_balance,
        available_balance=available_balance,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def run_dry_run_signal(config: MicroLiveConfig | None = None) -> MicroLiveDryRunSignalReport:
    resolved = config or load_config()
    blockers = validate_phase32(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []

    readonly = load_json(resolved.readonly_report_path)

    if resolved.require_readonly_passed:
        if not readonly:
            blockers.append("readonly_report_missing")
        elif readonly.get("passed") is not True:
            blockers.append("readonly_report_not_passed")

    notional = resolved.quantity * resolved.price
    risk_passed = True
    execution_contract_valid = True

    if notional <= 0:
        blockers.append("notional_must_be_positive")
        risk_passed = False

    if notional > resolved.max_order_notional_usd:
        blockers.append("notional_above_micro_live_limit")
        risk_passed = False

    if resolved.side.upper() not in {"BUY", "SELL"}:
        blockers.append("invalid_side")
        execution_contract_valid = False

    recommendations.append("Dry-run não envia ordem; apenas valida contrato de execução e envelope de risco.")
    recommendations.append("Só avance para ordem micro-live se este relatório e o read-only estiverem aprovados.")

    passed = not blockers and risk_passed and execution_contract_valid
    status, decision = final_status(passed, warnings)

    return MicroLiveDryRunSignalReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        side=resolved.side.upper(),
        quantity=resolved.quantity,
        price=resolved.price,
        notional_usd=notional,
        risk_passed=risk_passed,
        execution_contract_valid=execution_contract_valid,
        submitted=False,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def validate_real_order_unlock(config: MicroLiveConfig) -> list[str]:
    blockers = validate_live_config(config) + validate_phase32(config)

    if not config.allow_real_order_submission:
        blockers.append("micro_live_real_order_submission_not_allowed")

    if not config.allow_real_cancel:
        blockers.append("micro_live_real_cancel_not_allowed")

    if config.confirmation_phrase != "I_ACCEPT_MICRO_LIVE_RISK":
        blockers.append("micro_live_confirmation_phrase_required")

    if config.require_readonly_passed:
        readonly = load_json(config.readonly_report_path)
        if not readonly:
            blockers.append("readonly_report_missing")
        elif readonly.get("passed") is not True:
            blockers.append("readonly_report_not_passed")

    if config.require_dry_run_passed:
        dry_run = load_json(config.dry_run_report_path)
        if not dry_run:
            blockers.append("dry_run_report_missing")
        elif dry_run.get("passed") is not True:
            blockers.append("dry_run_report_not_passed")

    notional = config.quantity * config.price
    if notional > config.max_order_notional_usd:
        blockers.append("notional_above_micro_live_limit")

    return blockers


def run_small_order(config: MicroLiveConfig | None = None) -> MicroLiveSmallOrderReport:
    resolved = config or load_config()
    blockers = validate_real_order_unlock(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []

    test_order_passed = False
    submitted = False
    order_id = None
    client_order_id = None
    cancel_attempted = False
    cancel_passed = False
    fill_detected = False
    rejection_detected = False
    final_flat = False

    if not blockers:
        client = MicroLiveSignedClient(resolved)
        client_order_id = f"micro_live_{int(time.time())}"

        params = {
            "symbol": resolved.symbol,
            "side": resolved.side.upper(),
            "type": "LIMIT",
            "quantity": resolved.quantity,
            "price": resolved.price,
            "timeInForce": "GTC",
            "newClientOrderId": client_order_id,
            "newOrderRespType": "ACK",
        }

        test_order = client.signed_request(method="POST", path="/fapi/v1/order/test", params=params)
        test_order_passed = test_order.ok

        if not test_order.ok:
            blockers.append("live_test_order_not_passed")

        if test_order.ok:
            order = client.signed_request(method="POST", path="/fapi/v1/order", params=params)
            submitted = order.ok

            if not order.ok:
                blockers.append("micro_live_order_submit_failed")
                rejection_detected = True
            else:
                data = order.data or {}
                order_id = data.get("orderId")
                status = str(data.get("status", "")).upper()
                fill_detected = status in {"FILLED", "PARTIALLY_FILLED"}

                cancel_attempted = True
                cancel_params = {"symbol": resolved.symbol}

                if order_id:
                    cancel_params["orderId"] = order_id
                else:
                    cancel_params["origClientOrderId"] = client_order_id

                cancel = client.signed_request(method="DELETE", path="/fapi/v1/order", params=cancel_params)
                cancel_passed = cancel.ok

                if not cancel.ok and not fill_detected:
                    blockers.append("micro_live_cancel_failed")

        readonly_after = run_readonly_check(
            MicroLiveConfig(
                **{
                    **resolved.model_dump(),
                    "allow_real_order_submission": False,
                    "allow_real_cancel": False,
                    "require_no_live_flags_during_readonly": False,
                }
            )
        )
        final_flat = readonly_after.final_flat and readonly_after.open_orders_count == 0

        if not final_flat:
            blockers.append("post_order_final_flat_failed")

    recommendations.append("Após a micro-order, desligar imediatamente flags live de submit/cancel.")
    recommendations.append("Se cancelamento falhar ou posição não estiver flat, acionar kill switch e revisão manual.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return MicroLiveSmallOrderReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        side=resolved.side.upper(),
        quantity=resolved.quantity,
        price=resolved.price,
        test_order_passed=test_order_passed,
        submitted=submitted,
        order_id=order_id,
        client_order_id=client_order_id,
        cancel_attempted=cancel_attempted,
        cancel_passed=cancel_passed,
        final_flat=final_flat,
        fill_detected=fill_detected,
        rejection_detected=rejection_detected,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def run_kill_switch(config: MicroLiveConfig | None = None) -> LiveKillSwitchReport:
    resolved = config or load_config()
    blockers = validate_live_config(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []

    if not resolved.allow_kill_switch:
        blockers.append("kill_switch_not_allowed")

    cancel_all_attempted = False
    cancel_all_passed = False
    open_orders_after = None

    if not blockers:
        client = MicroLiveSignedClient(resolved)
        cancel_all_attempted = True

        cancel_all = client.signed_request(
            method="DELETE",
            path="/fapi/v1/allOpenOrders",
            params={"symbol": resolved.symbol},
        )
        cancel_all_passed = cancel_all.ok

        if not cancel_all.ok:
            blockers.append("cancel_all_open_orders_failed")

        open_orders = client.signed_request(method="GET", path="/fapi/v1/openOrders", params={"symbol": resolved.symbol})
        if open_orders.ok:
            open_orders_after = len(open_orders.data or [])
            if open_orders_after > 0:
                blockers.append("open_orders_remaining_after_kill_switch")
        else:
            blockers.append("open_orders_check_failed_after_kill_switch")

    recommendations.append("Kill switch deve ser usado apenas para emergência ou drill supervisionado.")
    recommendations.append("Depois do kill switch, rodar read-only e revisar manualmente.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return LiveKillSwitchReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        kill_switch_allowed=resolved.allow_kill_switch,
        cancel_all_attempted=cancel_all_attempted,
        cancel_all_passed=cancel_all_passed,
        open_orders_after=open_orders_after,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def build_session_report() -> MicroLiveSessionReport:
    config = load_config()

    readonly = load_json(config.readonly_report_path)
    dry_run = load_json(config.dry_run_report_path)
    small_order = load_json(config.output_dir / "first_micro_live_small_order.json")
    kill_switch = load_json(config.output_dir / "live_stop_kill_switch_validation.json")

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    readonly_passed = readonly.get("passed") is True
    dry_run_passed = dry_run.get("passed") is True
    small_order_passed = small_order.get("passed") is True if small_order else False
    kill_switch_passed = kill_switch.get("passed") is True if kill_switch else False

    final_flat = bool(
        small_order.get("final_flat", False)
        if small_order
        else readonly.get("final_flat", False)
    )
    open_orders_count = int(readonly.get("open_orders_count", 999))

    if not readonly_passed:
        blockers.append("readonly_not_passed")

    if not dry_run_passed:
        blockers.append("dry_run_not_passed")

    if small_order and not small_order_passed:
        blockers.append("small_order_not_passed")

    if not final_flat:
        blockers.append("final_flat_not_confirmed")

    if open_orders_count != 0:
        blockers.append("open_orders_detected")

    recommendations.append("Se small_order não foi executada, este relatório serve apenas como pre-live report.")
    recommendations.append("Se small_order foi executada, revisar fill/cancel/final_flat antes de qualquer nova ordem.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return MicroLiveSessionReport(
        status=status,
        passed=passed,
        decision=decision,
        readonly_passed=readonly_passed,
        dry_run_passed=dry_run_passed,
        small_order_passed=small_order_passed,
        kill_switch_passed=kill_switch_passed,
        final_flat=final_flat,
        open_orders_count=open_orders_count,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        metadata={
            "readonly_path": str(config.readonly_report_path),
            "dry_run_path": str(config.dry_run_report_path),
        },
    )