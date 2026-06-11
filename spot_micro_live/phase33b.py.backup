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
        clean: dict[str, Any] = {}
        for key, value in payload.items():
            normalized = str(key).lower()
            if any(item in normalized for item in sensitive):
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


class SpotMicroLiveConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/spot_micro_live")
    venue: str = "binance_spot"
    symbol: str = "BTCUSDT"
    base_asset: str = "BTC"
    quote_asset: str = "USDT"
    side: str = "BUY"
    quantity: float = 0.0001
    price: float = 60000.0
    rest_base_url: str = "https://api.binance.com"
    api_key: str = ""
    api_secret: str = ""
    recv_window: int = 5000
    timeout_seconds: int = 10

    phase32_report_path: Path = Path("artifacts/real_capital_gate/micro_live_preparation_gate_go_no_go.json")
    readonly_report_path: Path = Path("artifacts/spot_micro_live/spot_micro_live_readonly.json")
    dry_run_report_path: Path = Path("artifacts/spot_micro_live/spot_micro_live_dry_run_signal.json")
    small_order_report_path: Path = Path("artifacts/spot_micro_live/spot_micro_live_small_order.json")
    reconciliation_report_path: Path = Path("artifacts/spot_micro_live/spot_micro_live_reconciliation.json")
    kill_switch_report_path: Path = Path("artifacts/spot_micro_live/spot_micro_live_kill_switch.json")

    require_phase32_passed: bool = True
    require_readonly_passed: bool = True
    require_dry_run_passed: bool = True

    spot_reading_enabled_declared: bool = True
    spot_trading_enabled_declared: bool = False
    spot_withdrawals_enabled_declared: bool = False
    spot_internal_transfer_enabled_declared: bool = False
    spot_ip_restricted_declared: bool = False

    allow_real_order_submission: bool = False
    allow_real_cancel: bool = False
    allow_kill_switch: bool = False
    confirmation_phrase: str = ""

    max_order_notional_usd: float = 10.0
    max_daily_loss_usd: float = 5.0
    max_session_loss_usd: float = 2.0
    require_open_orders_zero: bool = True
    require_balance_reconciliation: bool = True


class SignedResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str = "binance_spot_signed_client"
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


class VenueAvailabilityReport(GateReport):
    source: str = "spot_live_venue_availability_check"
    selected_venue: str
    spot_live_selected: bool
    futures_live_required: bool
    futures_live_available: bool
    spot_live_available: bool
    jurisdiction: str


class SpotCredentialPermissionReport(GateReport):
    source: str = "binance_spot_credential_permission_check"
    api_key_present: bool
    api_secret_present: bool
    rest_base_url: str
    endpoint_is_spot: bool
    reading_enabled_declared: bool
    trading_enabled_declared: bool
    withdrawals_enabled_declared: bool
    internal_transfer_enabled_declared: bool
    ip_restricted_declared: bool


class SpotAccountReadOnlyReport(GateReport):
    source: str = "spot_account_readonly_snapshot"
    symbol: str
    base_asset: str
    quote_asset: str
    base_free: float
    base_locked: float
    quote_free: float
    quote_locked: float
    open_orders_count: int
    balances_read: bool
    open_orders_read: bool
    final_flat_equivalent: bool


class SpotDryRunExecutionContractReport(GateReport):
    source: str = "spot_dry_run_execution_contract"
    symbol: str
    side: str
    quantity: float
    price: float
    notional_usd: float
    risk_passed: bool
    execution_contract_valid: bool
    submitted: bool = False


class SpotSmallLimitOrderReport(GateReport):
    source: str = "spot_micro_live_small_limit_order"
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
    fill_detected: bool = False
    rejection_detected: bool = False
    final_reconciled: bool = False


class SpotReconciliationReport(GateReport):
    source: str = "spot_fill_cancel_reconciliation_review"
    symbol: str
    open_orders_count: int
    base_free: float
    base_locked: float
    quote_free: float
    quote_locked: float
    order_report_passed: bool
    order_submitted: bool
    cancel_passed: bool
    fill_detected: bool
    final_reconciled: bool


class SpotKillSwitchReport(GateReport):
    source: str = "spot_live_stop_kill_switch_validation"
    symbol: str
    kill_switch_allowed: bool
    cancel_all_attempted: bool = False
    cancel_all_passed: bool = False
    open_orders_after: int | None = None


class SpotMicroLiveSessionReport(GateReport):
    source: str = "spot_micro_live_session_report"
    venue_availability_passed: bool
    credential_permission_passed: bool
    readonly_passed: bool
    dry_run_passed: bool
    small_order_passed: bool
    reconciliation_passed: bool
    kill_switch_passed: bool
    open_orders_count: int
    final_reconciled: bool


def load_config() -> SpotMicroLiveConfig:
    return SpotMicroLiveConfig(
        output_dir=Path(os.getenv("SPOT_MICRO_LIVE_OUTPUT_DIR", "artifacts/spot_micro_live")),
        venue=os.getenv("MICRO_LIVE_VENUE", os.getenv("SPOT_MICRO_LIVE_VENUE", "binance_spot")),
        symbol=os.getenv("SPOT_MICRO_LIVE_SYMBOL", os.getenv("BINANCE_SPOT_SYMBOL", "BTCUSDT")),
        base_asset=os.getenv("SPOT_MICRO_LIVE_BASE_ASSET", os.getenv("BINANCE_SPOT_BASE_ASSET", "BTC")),
        quote_asset=os.getenv("SPOT_MICRO_LIVE_QUOTE_ASSET", os.getenv("BINANCE_SPOT_QUOTE_ASSET", "USDT")),
        side=os.getenv("SPOT_MICRO_LIVE_SIDE", "BUY"),
        quantity=env_float("SPOT_MICRO_LIVE_QUANTITY", env_float("MICRO_LIVE_QUANTITY", 0.0001)),
        price=env_float("SPOT_MICRO_LIVE_PRICE", env_float("MICRO_LIVE_PRICE", 60000.0)),
        rest_base_url=os.getenv("BINANCE_SPOT_REST_BASE_URL", "https://api.binance.com"),
        api_key=os.getenv("BINANCE_SPOT_API_KEY", ""),
        api_secret=os.getenv("BINANCE_SPOT_API_SECRET", ""),
        phase32_report_path=Path(os.getenv("SPOT_MICRO_LIVE_PHASE32_REPORT_PATH", "artifacts/real_capital_gate/micro_live_preparation_gate_go_no_go.json")),
        readonly_report_path=Path(os.getenv("SPOT_MICRO_LIVE_READONLY_REPORT_PATH", "artifacts/spot_micro_live/spot_micro_live_readonly.json")),
        dry_run_report_path=Path(os.getenv("SPOT_MICRO_LIVE_DRY_RUN_REPORT_PATH", "artifacts/spot_micro_live/spot_micro_live_dry_run_signal.json")),
        small_order_report_path=Path(os.getenv("SPOT_MICRO_LIVE_SMALL_ORDER_REPORT_PATH", "artifacts/spot_micro_live/spot_micro_live_small_order.json")),
        reconciliation_report_path=Path(os.getenv("SPOT_MICRO_LIVE_RECONCILIATION_REPORT_PATH", "artifacts/spot_micro_live/spot_micro_live_reconciliation.json")),
        spot_reading_enabled_declared=env_bool("BINANCE_SPOT_ENABLE_READING", True),
        spot_trading_enabled_declared=env_bool("BINANCE_SPOT_ENABLE_TRADING", False),
        spot_withdrawals_enabled_declared=env_bool("BINANCE_SPOT_ENABLE_WITHDRAWALS", False),
        spot_internal_transfer_enabled_declared=env_bool("BINANCE_SPOT_ENABLE_INTERNAL_TRANSFER", False),
        spot_ip_restricted_declared=env_bool("BINANCE_SPOT_IP_RESTRICTED", False),
        allow_real_order_submission=env_bool("SPOT_MICRO_LIVE_ALLOW_REAL_ORDER_SUBMISSION", False),
        allow_real_cancel=env_bool("SPOT_MICRO_LIVE_ALLOW_REAL_CANCEL", False),
        allow_kill_switch=env_bool("SPOT_MICRO_LIVE_ALLOW_KILL_SWITCH", False),
        confirmation_phrase=os.getenv("SPOT_MICRO_LIVE_CONFIRM_PHRASE", ""),
        max_order_notional_usd=env_float("SPOT_MICRO_LIVE_MAX_ORDER_NOTIONAL_USD", 10.0),
        max_daily_loss_usd=env_float("SPOT_MICRO_LIVE_MAX_DAILY_LOSS_USD", 5.0),
        max_session_loss_usd=env_float("SPOT_MICRO_LIVE_MAX_SESSION_LOSS_USD", 2.0),
        require_phase32_passed=env_bool("SPOT_MICRO_LIVE_REQUIRE_PHASE32_PASSED", True),
        require_readonly_passed=env_bool("SPOT_MICRO_LIVE_REQUIRE_READONLY_PASSED", True),
        require_dry_run_passed=env_bool("SPOT_MICRO_LIVE_REQUIRE_DRY_RUN_PASSED", True),
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


class BinanceSpotSignedClient:
    def __init__(self, config: SpotMicroLiveConfig):
        self.config = config

    def sanitized_config(self) -> dict[str, Any]:
        return sanitize_payload(self.config.model_dump(mode="json"))

    def _sign(self, params: dict[str, Any]) -> str:
        query = urlencode(params, doseq=True)
        return hmac.new(self.config.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()

    def signed_request(self, *, method: str, path: str, params: dict[str, Any] | None = None) -> SignedResponse:
        resolved = dict(params or {})
        resolved["recvWindow"] = self.config.recv_window
        resolved["timestamp"] = int(time.time() * 1000)
        query_without_signature = urlencode(resolved, doseq=True)
        resolved["signature"] = self._sign(resolved)
        url = f"{self.config.rest_base_url.rstrip('/')}{path}?{urlencode(resolved, doseq=True)}"
        sanitized_url = f"{self.config.rest_base_url.rstrip('/')}{path}?{query_without_signature}&signature=***"
        headers = {"X-MBX-APIKEY": self.config.api_key}
        try:
            response = requests.request(method=method.upper(), url=url, headers=headers, timeout=self.config.timeout_seconds)
            try:
                data = response.json()
            except ValueError:
                data = response.text
            return SignedResponse(
                status="OK" if response.ok else "ERROR",
                ok=response.ok,
                method=method.upper(),
                path=path,
                url=sanitized_url,
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
                url=sanitized_url,
                error_message=str(exc),
                config=self.sanitized_config(),
            )


def validate_spot_config(config: SpotMicroLiveConfig) -> list[str]:
    blockers: list[str] = []
    if config.venue != "binance_spot":
        blockers.append("selected_venue_must_be_binance_spot")
    if not config.api_key.strip():
        blockers.append("spot_api_key_required")
    if not config.api_secret.strip():
        blockers.append("spot_api_secret_required")
    if not config.rest_base_url.startswith("https://"):
        blockers.append("https_spot_endpoint_required")
    lower_url = config.rest_base_url.lower()
    if "fapi" in lower_url or "testnet" in lower_url or "demo" in lower_url:
        blockers.append("spot_endpoint_expected_not_futures_or_testnet")
    return blockers


def validate_phase32(config: SpotMicroLiveConfig) -> list[str]:
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


def extract_balance(account_data: dict[str, Any], asset: str) -> tuple[float, float]:
    for item in account_data.get("balances", []) or []:
        if str(item.get("asset", "")).upper() == asset.upper():
            return float(item.get("free", 0) or 0), float(item.get("locked", 0) or 0)
    return 0.0, 0.0


def run_venue_availability_check(config: SpotMicroLiveConfig | None = None) -> VenueAvailabilityReport:
    resolved = config or load_config()
    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    jurisdiction = os.getenv("APP_JURISDICTION", os.getenv("APP_COUNTRY", "Brazil"))
    futures_live_available = env_bool("BINANCE_FUTURES_LIVE_TRADING_ALLOWED", False)
    spot_live_available = env_bool("BINANCE_SPOT_ENABLED", True)
    futures_live_required = False
    spot_live_selected = resolved.venue == "binance_spot"
    if not spot_live_selected:
        blockers.append("binance_spot_must_be_selected_for_brazil_live")
    if not spot_live_available:
        blockers.append("binance_spot_not_available_or_not_enabled")
    recommendations.append("Futures live deve permanecer fora do caminho crítico para operador no Brasil.")
    recommendations.append("Spot live é o venue selecionado para microcapital real.")
    recommendations.append("Futures pode permanecer para testnet, paper, backtest e market data.")
    passed = not blockers
    status, decision = final_status(passed, warnings)
    return VenueAvailabilityReport(
        status=status,
        passed=passed,
        decision=decision,
        selected_venue=resolved.venue,
        spot_live_selected=spot_live_selected,
        futures_live_required=futures_live_required,
        futures_live_available=futures_live_available,
        spot_live_available=spot_live_available,
        jurisdiction=jurisdiction,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def run_spot_credential_permission_check(config: SpotMicroLiveConfig | None = None) -> SpotCredentialPermissionReport:
    resolved = config or load_config()
    blockers = validate_spot_config(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []
    endpoint_is_spot = "api.binance.com" in resolved.rest_base_url.lower() and "fapi" not in resolved.rest_base_url.lower()
    if not endpoint_is_spot:
        blockers.append("binance_spot_endpoint_not_detected")
    if not resolved.spot_reading_enabled_declared:
        blockers.append("spot_reading_permission_not_declared_enabled")
    if not resolved.spot_trading_enabled_declared:
        warnings.append("spot_trading_permission_not_declared_enabled")
    if resolved.spot_withdrawals_enabled_declared:
        blockers.append("spot_withdrawals_permission_must_be_disabled_for_trading_bot")
    if resolved.spot_internal_transfer_enabled_declared:
        blockers.append("spot_internal_transfer_permission_must_be_disabled_for_trading_bot")
    if not resolved.spot_ip_restricted_declared:
        warnings.append("spot_ip_restriction_not_declared")
    recommendations.append("Trading pode ficar OFF durante read-only/dry-run e só ligar antes de ordem pequena.")
    recommendations.append("Withdrawals devem ficar OFF na API de trading; saques de lucro devem ser processo separado.")
    recommendations.append("Use IP restriction quando possível.")
    passed = not blockers
    status, decision = final_status(passed, warnings)
    return SpotCredentialPermissionReport(
        status=status,
        passed=passed,
        decision=decision,
        api_key_present=bool(resolved.api_key.strip()),
        api_secret_present=bool(resolved.api_secret.strip()),
        rest_base_url=resolved.rest_base_url,
        endpoint_is_spot=endpoint_is_spot,
        reading_enabled_declared=resolved.spot_reading_enabled_declared,
        trading_enabled_declared=resolved.spot_trading_enabled_declared,
        withdrawals_enabled_declared=resolved.spot_withdrawals_enabled_declared,
        internal_transfer_enabled_declared=resolved.spot_internal_transfer_enabled_declared,
        ip_restricted_declared=resolved.spot_ip_restricted_declared,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def run_spot_readonly_snapshot(config: SpotMicroLiveConfig | None = None) -> SpotAccountReadOnlyReport:
    resolved = config or load_config()
    blockers = validate_spot_config(resolved) + validate_phase32(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []
    base_free = 0.0
    base_locked = 0.0
    quote_free = 0.0
    quote_locked = 0.0
    open_orders_count = 0
    balances_read = False
    open_orders_read = False
    if env_bool("SPOT_MICRO_LIVE_ALLOW_REAL_ORDER_SUBMISSION", False):
        blockers.append("spot_real_order_submission_must_be_disabled_for_readonly")
    if env_bool("SPOT_MICRO_LIVE_ALLOW_REAL_CANCEL", False):
        blockers.append("spot_real_cancel_must_be_disabled_for_readonly")
    if not blockers:
        client = BinanceSpotSignedClient(resolved)
        account = client.signed_request(method="GET", path="/api/v3/account")
        open_orders = client.signed_request(method="GET", path="/api/v3/openOrders", params={"symbol": resolved.symbol})
        if not account.ok:
            blockers.append("spot_account_request_failed")
        else:
            balances_read = True
            base_free, base_locked = extract_balance(account.data or {}, resolved.base_asset)
            quote_free, quote_locked = extract_balance(account.data or {}, resolved.quote_asset)
        if not open_orders.ok:
            blockers.append("spot_open_orders_request_failed")
        else:
            open_orders_read = True
            open_orders_count = len(open_orders.data or [])
        if open_orders_count > 0:
            blockers.append("spot_open_orders_detected")
    final_flat_equivalent = open_orders_count == 0 and base_locked == 0.0
    if resolved.require_open_orders_zero and open_orders_count != 0:
        blockers.append("spot_open_orders_must_be_zero")
    recommendations.append("Spot read-only deve confirmar balances e ordens abertas sem permitir submit/cancel.")
    recommendations.append("Em Spot, reconciliação usa balances BTC/USDT e open orders, não positionAmt de futures.")
    passed = not blockers
    status, decision = final_status(passed, warnings)
    return SpotAccountReadOnlyReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        base_asset=resolved.base_asset,
        quote_asset=resolved.quote_asset,
        base_free=base_free,
        base_locked=base_locked,
        quote_free=quote_free,
        quote_locked=quote_locked,
        open_orders_count=open_orders_count,
        balances_read=balances_read,
        open_orders_read=open_orders_read,
        final_flat_equivalent=final_flat_equivalent,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def run_spot_dry_run_execution_contract(config: SpotMicroLiveConfig | None = None) -> SpotDryRunExecutionContractReport:
    resolved = config or load_config()
    blockers = validate_phase32(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []
    if resolved.require_readonly_passed:
        readonly = load_json(resolved.readonly_report_path)
        if not readonly:
            blockers.append("spot_readonly_report_missing")
        elif readonly.get("passed") is not True:
            blockers.append("spot_readonly_report_not_passed")
    notional = resolved.quantity * resolved.price
    risk_passed = True
    execution_contract_valid = True
    if resolved.side.upper() not in {"BUY", "SELL"}:
        blockers.append("invalid_spot_side")
        execution_contract_valid = False
    if resolved.quantity <= 0:
        blockers.append("quantity_must_be_positive")
        risk_passed = False
    if resolved.price <= 0:
        blockers.append("price_must_be_positive")
        risk_passed = False
    if notional <= 0:
        blockers.append("notional_must_be_positive")
        risk_passed = False
    if notional > resolved.max_order_notional_usd:
        blockers.append("notional_above_spot_micro_live_limit")
        risk_passed = False
    recommendations.append("Dry-run Spot não envia ordem; apenas valida contrato e envelope de risco.")
    recommendations.append("Só avance para ordem real após read-only e dry-run aprovados.")
    passed = not blockers and risk_passed and execution_contract_valid
    status, decision = final_status(passed, warnings)
    return SpotDryRunExecutionContractReport(
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


def validate_small_order_unlock(config: SpotMicroLiveConfig) -> list[str]:
    blockers = validate_spot_config(config) + validate_phase32(config)
    if not config.allow_real_order_submission:
        blockers.append("spot_real_order_submission_not_allowed")
    if not config.allow_real_cancel:
        blockers.append("spot_real_cancel_not_allowed")
    if config.confirmation_phrase != "I_ACCEPT_SPOT_MICRO_LIVE_RISK":
        blockers.append("spot_micro_live_confirmation_phrase_required")
    if config.require_readonly_passed:
        readonly = load_json(config.readonly_report_path)
        if not readonly:
            blockers.append("spot_readonly_report_missing")
        elif readonly.get("passed") is not True:
            blockers.append("spot_readonly_report_not_passed")
    if config.require_dry_run_passed:
        dry_run = load_json(config.dry_run_report_path)
        if not dry_run:
            blockers.append("spot_dry_run_report_missing")
        elif dry_run.get("passed") is not True:
            blockers.append("spot_dry_run_report_not_passed")
    if config.quantity * config.price > config.max_order_notional_usd:
        blockers.append("notional_above_spot_micro_live_limit")
    return blockers


def run_spot_small_limit_order(config: SpotMicroLiveConfig | None = None) -> SpotSmallLimitOrderReport:
    resolved = config or load_config()
    blockers = validate_small_order_unlock(resolved)
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
    final_reconciled = False
    if not blockers:
        client = BinanceSpotSignedClient(resolved)
        client_order_id = f"spot_micro_live_{int(time.time())}"
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
        test_order = client.signed_request(method="POST", path="/api/v3/order/test", params=params)
        test_order_passed = test_order.ok
        if not test_order.ok:
            blockers.append("spot_test_order_not_passed")
        if test_order.ok:
            order = client.signed_request(method="POST", path="/api/v3/order", params=params)
            submitted = order.ok
            if not order.ok:
                blockers.append("spot_order_submit_failed")
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
                cancel = client.signed_request(method="DELETE", path="/api/v3/order", params=cancel_params)
                cancel_passed = cancel.ok
                if not cancel.ok and not fill_detected:
                    blockers.append("spot_order_cancel_failed")
        reconciliation_config = SpotMicroLiveConfig(**{**resolved.model_dump(), "allow_real_order_submission": False, "allow_real_cancel": False})
        reconciliation = run_spot_reconciliation(
            reconciliation_config,
            order_report_override={
                "passed": not blockers,
                "submitted": submitted,
                "cancel_passed": cancel_passed,
                "fill_detected": fill_detected,
            },
        )
        final_reconciled = reconciliation.final_reconciled
        if not final_reconciled:
            blockers.append("spot_post_order_reconciliation_failed")
    recommendations.append("Após qualquer ordem Spot, desligar flags de submit/cancel.")
    recommendations.append("Se cancelamento falhar ou houver ordem aberta, acionar kill switch e revisão manual.")
    passed = not blockers
    status, decision = final_status(passed, warnings)
    return SpotSmallLimitOrderReport(
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
        fill_detected=fill_detected,
        rejection_detected=rejection_detected,
        final_reconciled=final_reconciled,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def run_spot_reconciliation(
    config: SpotMicroLiveConfig | None = None,
    *,
    order_report_override: dict[str, Any] | None = None,
) -> SpotReconciliationReport:
    resolved = config or load_config()
    blockers = validate_spot_config(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []
    open_orders_count = 0
    base_free = 0.0
    base_locked = 0.0
    quote_free = 0.0
    quote_locked = 0.0
    order_report = order_report_override or load_json(resolved.small_order_report_path)
    if not order_report:
        blockers.append("spot_small_order_report_missing")
    if not blockers:
        client = BinanceSpotSignedClient(resolved)
        account = client.signed_request(method="GET", path="/api/v3/account")
        open_orders = client.signed_request(method="GET", path="/api/v3/openOrders", params={"symbol": resolved.symbol})
        if not account.ok:
            blockers.append("spot_reconciliation_account_request_failed")
        else:
            base_free, base_locked = extract_balance(account.data or {}, resolved.base_asset)
            quote_free, quote_locked = extract_balance(account.data or {}, resolved.quote_asset)
        if not open_orders.ok:
            blockers.append("spot_reconciliation_open_orders_request_failed")
        else:
            open_orders_count = len(open_orders.data or [])
        if open_orders_count > 0:
            blockers.append("spot_open_orders_remaining_after_reconciliation")
        if base_locked > 0:
            blockers.append("spot_base_asset_locked_after_reconciliation")
        if quote_locked > 0:
            warnings.append("spot_quote_asset_locked_after_reconciliation_review_needed")
    order_report_passed = order_report.get("passed") is True
    order_submitted = order_report.get("submitted") is True
    cancel_passed = order_report.get("cancel_passed") is True
    fill_detected = order_report.get("fill_detected") is True
    final_reconciled = not blockers and open_orders_count == 0 and base_locked == 0
    recommendations.append("Spot reconciliation deve confirmar open_orders=0 e balances locked esperados.")
    recommendations.append("Fill em Spot altera saldo BTC/USDT; não existe positionAmt como em Futures.")
    passed = not blockers
    status, decision = final_status(passed, warnings)
    return SpotReconciliationReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        open_orders_count=open_orders_count,
        base_free=base_free,
        base_locked=base_locked,
        quote_free=quote_free,
        quote_locked=quote_locked,
        order_report_passed=order_report_passed,
        order_submitted=order_submitted,
        cancel_passed=cancel_passed,
        fill_detected=fill_detected,
        final_reconciled=final_reconciled,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def run_spot_kill_switch(config: SpotMicroLiveConfig | None = None) -> SpotKillSwitchReport:
    resolved = config or load_config()
    blockers = validate_spot_config(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []
    if not resolved.allow_kill_switch:
        blockers.append("spot_kill_switch_not_allowed")
    cancel_all_attempted = False
    cancel_all_passed = False
    open_orders_after = None
    if not blockers:
        client = BinanceSpotSignedClient(resolved)
        cancel_all_attempted = True
        cancel_all = client.signed_request(method="DELETE", path="/api/v3/openOrders", params={"symbol": resolved.symbol})
        cancel_all_passed = cancel_all.ok
        if not cancel_all.ok:
            blockers.append("spot_cancel_all_open_orders_failed")
        open_orders = client.signed_request(method="GET", path="/api/v3/openOrders", params={"symbol": resolved.symbol})
        if open_orders.ok:
            open_orders_after = len(open_orders.data or [])
            if open_orders_after > 0:
                blockers.append("spot_open_orders_remaining_after_kill_switch")
        else:
            blockers.append("spot_open_orders_check_failed_after_kill_switch")
    recommendations.append("Kill switch Spot cancela todas as ordens abertas do símbolo.")
    recommendations.append("Depois do kill switch, rodar read-only/reconciliation.")
    passed = not blockers
    status, decision = final_status(passed, warnings)
    return SpotKillSwitchReport(
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


def build_spot_session_report(config: SpotMicroLiveConfig | None = None) -> SpotMicroLiveSessionReport:
    resolved = config or load_config()
    venue = load_json(resolved.output_dir / "spot_venue_availability.json")
    credential = load_json(resolved.output_dir / "spot_credential_permission.json")
    readonly = load_json(resolved.readonly_report_path)
    dry_run = load_json(resolved.dry_run_report_path)
    small_order = load_json(resolved.small_order_report_path)
    reconciliation = load_json(resolved.reconciliation_report_path)
    kill_switch = load_json(resolved.kill_switch_report_path)
    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    venue_passed = venue.get("passed") is True
    credential_passed = credential.get("passed") is True
    readonly_passed = readonly.get("passed") is True
    dry_run_passed = dry_run.get("passed") is True
    small_order_passed = small_order.get("passed") is True if small_order else False
    reconciliation_passed = reconciliation.get("passed") is True if reconciliation else False
    kill_switch_passed = kill_switch.get("passed") is True if kill_switch else False
    open_orders_count = int(reconciliation.get("open_orders_count", readonly.get("open_orders_count", 999)) if reconciliation or readonly else 999)
    final_reconciled = bool(reconciliation.get("final_reconciled", False) if reconciliation else readonly.get("final_flat_equivalent", False))
    if not venue_passed:
        blockers.append("venue_availability_not_passed")
    if not credential_passed:
        blockers.append("credential_permission_not_passed")
    if not readonly_passed:
        blockers.append("readonly_not_passed")
    if not dry_run_passed:
        blockers.append("dry_run_not_passed")
    if small_order and not small_order_passed:
        blockers.append("small_order_not_passed")
    if small_order and not reconciliation_passed:
        blockers.append("reconciliation_not_passed")
    if open_orders_count != 0:
        blockers.append("open_orders_detected")
    if not final_reconciled:
        blockers.append("final_reconciliation_not_confirmed")
    recommendations.append("Se small_order não foi executada, este é relatório pre-live Spot.")
    recommendations.append("Se small_order foi executada, revisar order/cancel/reconciliation antes de nova ordem.")
    recommendations.append("Manter withdrawals OFF na API de trading; saques são processo separado.")
    passed = not blockers
    status, decision = final_status(passed, warnings)
    return SpotMicroLiveSessionReport(
        status=status,
        passed=passed,
        decision=decision,
        venue_availability_passed=venue_passed,
        credential_permission_passed=credential_passed,
        readonly_passed=readonly_passed,
        dry_run_passed=dry_run_passed,
        small_order_passed=small_order_passed,
        reconciliation_passed=reconciliation_passed,
        kill_switch_passed=kill_switch_passed,
        open_orders_count=open_orders_count,
        final_reconciled=final_reconciled,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        metadata={
            "venue_report": str(resolved.output_dir / "spot_venue_availability.json"),
            "credential_report": str(resolved.output_dir / "spot_credential_permission.json"),
            "readonly_report": str(resolved.readonly_report_path),
            "dry_run_report": str(resolved.dry_run_report_path),
            "small_order_report": str(resolved.small_order_report_path),
            "reconciliation_report": str(resolved.reconciliation_report_path),
            "kill_switch_report": str(resolved.kill_switch_report_path),
        },
    )
