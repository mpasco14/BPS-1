from __future__ import annotations
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode
import math
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

def env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
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

    # Venue principal da Fase 33B.
    venue: str = "binance_spot"
    jurisdiction: str = "Brazil"

    # Modo Spot BRL.
    symbol: str = "BTCBRL"
    base_asset: str = "BTC"
    quote_asset: str = "BRL"

    side: str = "BUY"

    # Modo BRL: ordem por valor cotado.
    # Exemplo: comprar aproximadamente 10 BRL de BTC.
    order_quote_amount: float = 10.0
    min_order_quote_amount: float = 10.0
    max_order_quote_amount: float = 20.0

    # Envelope de capital/risk em BRL.
    total_capital_quote: float = 100.0
    max_daily_loss_quote: float = 5.0
    max_session_loss_quote: float = 2.0
    min_gross_profit_target_pct: float = 0.005

    # Se price <= 0, o sistema usa ticker atual da Binance.
    price: float = 0.0

    # Se quantity <= 0, o sistema calcula:
    # quantity = order_quote_amount / price
    quantity: float = 0.0

    # Binance Spot REST.
    rest_base_url: str = "https://api.binance.com"
    api_key: str = ""
    api_secret: str = ""
    recv_window: int = 5000
    timeout_seconds: int = 10

    # Relatórios/artifacts.
    phase32_report_path: Path = Path(
        "artifacts/real_capital_gate/micro_live_preparation_gate_go_no_go.json"
    )
    venue_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_venue_availability.json"
    )
    credential_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_credential_permission.json"
    )
    pair_discovery_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_brl_pair_discovery.json"
    )
    filter_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_brl_filter_validation.json"
    )
    readonly_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_micro_live_readonly.json"
    )
    dry_run_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_micro_live_dry_run_signal.json"
    )
    small_order_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_micro_live_small_order.json"
    )
    reconciliation_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_micro_live_reconciliation.json"
    )
    kill_switch_report_path: Path = Path(
        "artifacts/spot_micro_live/spot_micro_live_kill_switch.json"
    )

    # Dependências obrigatórias entre gates.
    require_phase32_passed: bool = True
    require_venue_passed: bool = True
    require_credential_passed: bool = True
    require_pair_discovery_passed: bool = True
    require_filter_validation_passed: bool = True
    require_readonly_passed: bool = True
    require_dry_run_passed: bool = True

    # Declarações manuais da API Spot.
    spot_reading_enabled_declared: bool = True
    spot_trading_enabled_declared: bool = False
    spot_withdrawals_enabled_declared: bool = False
    spot_internal_transfer_enabled_declared: bool = False
    spot_ip_restricted_declared: bool = False

    # Execução real bloqueada por padrão.
    allow_real_order_submission: bool = False
    allow_real_cancel: bool = False
    allow_kill_switch: bool = False
    confirmation_phrase: str = ""

    # Regras de segurança da sessão.
    max_open_orders: int = 1
    max_orders_per_session: int = 3
    market_orders_allowed: bool = False
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
    quote_asset_required: str


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

class SpotPairDiscoveryReport(GateReport):
    source: str = "spot_brl_pair_discovery"

    quote_asset: str
    selected_symbol: str
    selected_symbol_available: bool
    trading_pairs_count: int
    trading_pairs: list[str] = Field(default_factory=list)


class SpotFilterValidationReport(GateReport):
    source: str = "spot_brl_symbol_filter_validation"

    symbol: str
    status_symbol: str
    base_asset: str
    quote_asset: str

    current_price: float
    requested_quote_amount: float
    computed_quantity: float
    rounded_quantity: str
    rounded_price: str
    resulting_notional: float

    min_notional: float | None = None
    max_notional: float | None = None
    step_size: str | None = None
    min_qty: float | None = None
    tick_size: str | None = None

    min_gross_profit_target_pct: float

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
    sufficient_quote_for_test_order: bool


class SpotDryRunExecutionContractReport(GateReport):
    source: str = "spot_dry_run_execution_contract"

    symbol: str
    side: str
    quantity: str
    price: str
    quote_asset: str
    notional_quote: float

    risk_passed: bool
    execution_contract_valid: bool
    target_gross_profit_pct: float
    submitted: bool = False


class SpotSmallLimitOrderReport(GateReport):
    source: str = "spot_micro_live_small_limit_order"

    symbol: str
    side: str
    quantity: str
    price: str
    quote_asset: str
    notional_quote: float

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
        output_dir=Path(
            os.getenv("SPOT_MICRO_LIVE_OUTPUT_DIR", "artifacts/spot_micro_live")
        ),

        venue=os.getenv(
            "MICRO_LIVE_VENUE",
            os.getenv("SPOT_MICRO_LIVE_VENUE", "binance_spot"),
        ),
        jurisdiction=os.getenv(
            "APP_JURISDICTION",
            os.getenv("APP_COUNTRY", "Brazil"),
        ),

        symbol=os.getenv(
            "SPOT_MICRO_LIVE_SYMBOL",
            os.getenv("BINANCE_SPOT_SYMBOL", "BTCBRL"),
        ),
        base_asset=os.getenv(
            "SPOT_MICRO_LIVE_BASE_ASSET",
            os.getenv("BINANCE_SPOT_BASE_ASSET", "BTC"),
        ),
        quote_asset=os.getenv(
            "SPOT_MICRO_LIVE_QUOTE_ASSET",
            os.getenv("BINANCE_SPOT_QUOTE_ASSET", "BRL"),
        ),

        side=os.getenv("SPOT_MICRO_LIVE_SIDE", "BUY"),

        order_quote_amount=env_float(
            "SPOT_MICRO_LIVE_ORDER_QUOTE_BRL",
            env_float("SPOT_MICRO_LIVE_ORDER_QUOTE_AMOUNT", 15.0),
        ),
        min_order_quote_amount=env_float(
            "SPOT_MICRO_LIVE_MIN_ORDER_QUOTE_BRL",
            10.0,
        ),
        max_order_quote_amount=env_float(
            "SPOT_MICRO_LIVE_MAX_ORDER_QUOTE_BRL",
            20.0,
        ),

        total_capital_quote=env_float(
            "SPOT_MICRO_LIVE_TOTAL_CAPITAL_BRL",
            100.0,
        ),
        max_daily_loss_quote=env_float(
            "SPOT_MICRO_LIVE_MAX_DAILY_LOSS_BRL",
            5.0,
        ),
        max_session_loss_quote=env_float(
            "SPOT_MICRO_LIVE_MAX_SESSION_LOSS_BRL",
            2.0,
        ),
        min_gross_profit_target_pct=env_float(
            "SPOT_MICRO_LIVE_MIN_GROSS_PROFIT_TARGET_PCT",
            0.005,
        ),

        price=env_float("SPOT_MICRO_LIVE_PRICE", 0.0),
        quantity=env_float("SPOT_MICRO_LIVE_QUANTITY", 0.0),

        rest_base_url=os.getenv(
            "BINANCE_SPOT_REST_BASE_URL",
            "https://api.binance.com",
        ),
        api_key=os.getenv("BINANCE_SPOT_API_KEY", ""),
        api_secret=os.getenv("BINANCE_SPOT_API_SECRET", ""),
        recv_window=env_int("SPOT_MICRO_LIVE_RECV_WINDOW", 5000),
        timeout_seconds=env_int("SPOT_MICRO_LIVE_TIMEOUT_SECONDS", 10),

        phase32_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_PHASE32_REPORT_PATH",
                "artifacts/real_capital_gate/micro_live_preparation_gate_go_no_go.json",
            )
        ),
        venue_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_VENUE_REPORT_PATH",
                "artifacts/spot_micro_live/spot_venue_availability.json",
            )
        ),
        credential_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_CREDENTIAL_REPORT_PATH",
                "artifacts/spot_micro_live/spot_credential_permission.json",
            )
        ),
        pair_discovery_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_PAIR_DISCOVERY_REPORT_PATH",
                "artifacts/spot_micro_live/spot_brl_pair_discovery.json",
            )
        ),
        filter_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_FILTER_REPORT_PATH",
                "artifacts/spot_micro_live/spot_brl_filter_validation.json",
            )
        ),
        readonly_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_READONLY_REPORT_PATH",
                "artifacts/spot_micro_live/spot_micro_live_readonly.json",
            )
        ),
        dry_run_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_DRY_RUN_REPORT_PATH",
                "artifacts/spot_micro_live/spot_micro_live_dry_run_signal.json",
            )
        ),
        small_order_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_SMALL_ORDER_REPORT_PATH",
                "artifacts/spot_micro_live/spot_micro_live_small_order.json",
            )
        ),
        reconciliation_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_RECONCILIATION_REPORT_PATH",
                "artifacts/spot_micro_live/spot_micro_live_reconciliation.json",
            )
        ),
        kill_switch_report_path=Path(
            os.getenv(
                "SPOT_MICRO_LIVE_KILL_SWITCH_REPORT_PATH",
                "artifacts/spot_micro_live/spot_micro_live_kill_switch.json",
            )
        ),

        require_phase32_passed=env_bool(
            "SPOT_MICRO_LIVE_REQUIRE_PHASE32_PASSED",
            True,
        ),
        require_venue_passed=env_bool(
            "SPOT_MICRO_LIVE_REQUIRE_VENUE_PASSED",
            True,
        ),
        require_credential_passed=env_bool(
            "SPOT_MICRO_LIVE_REQUIRE_CREDENTIAL_PASSED",
            True,
        ),
        require_pair_discovery_passed=env_bool(
            "SPOT_MICRO_LIVE_REQUIRE_PAIR_DISCOVERY_PASSED",
            True,
        ),
        require_filter_validation_passed=env_bool(
            "SPOT_MICRO_LIVE_REQUIRE_FILTER_VALIDATION_PASSED",
            True,
        ),
        require_readonly_passed=env_bool(
            "SPOT_MICRO_LIVE_REQUIRE_READONLY_PASSED",
            True,
        ),
        require_dry_run_passed=env_bool(
            "SPOT_MICRO_LIVE_REQUIRE_DRY_RUN_PASSED",
            True,
        ),

        spot_reading_enabled_declared=env_bool(
            "BINANCE_SPOT_ENABLE_READING",
            True,
        ),
        spot_trading_enabled_declared=env_bool(
            "BINANCE_SPOT_ENABLE_TRADING",
            False,
        ),
        spot_withdrawals_enabled_declared=env_bool(
            "BINANCE_SPOT_ENABLE_WITHDRAWALS",
            False,
        ),
        spot_internal_transfer_enabled_declared=env_bool(
            "BINANCE_SPOT_ENABLE_INTERNAL_TRANSFER",
            False,
        ),
        spot_ip_restricted_declared=env_bool(
            "BINANCE_SPOT_IP_RESTRICTED",
            False,
        ),

        allow_real_order_submission=env_bool(
            "SPOT_MICRO_LIVE_ALLOW_REAL_ORDER_SUBMISSION",
            False,
        ),
        allow_real_cancel=env_bool(
            "SPOT_MICRO_LIVE_ALLOW_REAL_CANCEL",
            False,
        ),
        allow_kill_switch=env_bool(
            "SPOT_MICRO_LIVE_ALLOW_KILL_SWITCH",
            False,
        ),
        confirmation_phrase=os.getenv(
            "SPOT_MICRO_LIVE_CONFIRM_PHRASE",
            "",
        ),

        max_open_orders=env_int("SPOT_MICRO_LIVE_MAX_OPEN_ORDERS", 1),
        max_orders_per_session=env_int(
            "SPOT_MICRO_LIVE_MAX_ORDERS_PER_SESSION",
            3,
        ),
        market_orders_allowed=env_bool(
            "SPOT_MICRO_LIVE_MARKET_ORDERS_ALLOWED",
            False,
        ),
        require_open_orders_zero=env_bool(
            "SPOT_MICRO_LIVE_REQUIRE_OPEN_ORDERS_ZERO",
            True,
        ),
        require_balance_reconciliation=env_bool(
            "SPOT_MICRO_LIVE_REQUIRE_BALANCE_RECONCILIATION",
            True,
        ),
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

def decimal_floor_to_step(value: float, step: str) -> str:
    try:
        value_d = Decimal(str(value))
        step_d = Decimal(str(step))
    except InvalidOperation:
        return str(value)

    if step_d <= 0:
        return format(value_d.normalize(), "f")

    floored = (value_d / step_d).to_integral_value(rounding=ROUND_DOWN) * step_d

    return format(floored.normalize(), "f")


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def public_get(
    config: SpotMicroLiveConfig,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{config.rest_base_url.rstrip('/')}{path}"
    response = requests.get(
        url,
        params=params or {},
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def get_symbol_info(config: SpotMicroLiveConfig) -> dict[str, Any]:
    data = public_get(
        config,
        "/api/v3/exchangeInfo",
        {"symbol": config.symbol},
    )

    symbols = data.get("symbols", []) or []

    if not symbols:
        return {}

    return symbols[0]


def get_brl_pairs(config: SpotMicroLiveConfig) -> list[str]:
    data = public_get(config, "/api/v3/exchangeInfo")

    return sorted(
        symbol_data["symbol"]
        for symbol_data in data.get("symbols", []) or []
        if symbol_data.get("quoteAsset") == config.quote_asset
        and symbol_data.get("status") == "TRADING"
    )


def get_current_price(config: SpotMicroLiveConfig) -> float:
    if config.price and config.price > 0:
        return config.price

    data = public_get(
        config,
        "/api/v3/ticker/price",
        {"symbol": config.symbol},
    )

    return to_float(data.get("price"), 0.0)


def filters_by_type(symbol_info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item.get("filterType"): item
        for item in symbol_info.get("filters", []) or []
    }


def notional_bounds(
    filters: dict[str, dict[str, Any]],
) -> tuple[float | None, float | None]:
    notional_filter = filters.get("NOTIONAL")
    min_notional_filter = filters.get("MIN_NOTIONAL")

    if notional_filter:
        min_notional = to_float(notional_filter.get("minNotional"), 0.0)
        max_notional = to_float(notional_filter.get("maxNotional"), 0.0)

        return min_notional or None, max_notional or None

    if min_notional_filter:
        min_notional = to_float(min_notional_filter.get("minNotional"), 0.0)

        return min_notional or None, None

    return None, None


def build_order_contract(
    config: SpotMicroLiveConfig,
) -> tuple[str, str, float, dict[str, Any]]:
    symbol_info = get_symbol_info(config)
    filters = filters_by_type(symbol_info)

    lot_size = filters.get("LOT_SIZE", {})
    price_filter = filters.get("PRICE_FILTER", {})

    step_size = lot_size.get("stepSize", "0.00000001")
    tick_size = price_filter.get("tickSize", "0.01")

    price = get_current_price(config)
    rounded_price = decimal_floor_to_step(price, tick_size)

    if config.quantity and config.quantity > 0:
        raw_quantity = config.quantity
    else:
        raw_quantity = config.order_quote_amount / max(price, 1e-12)

    rounded_quantity = decimal_floor_to_step(raw_quantity, step_size)

    notional = float(
        Decimal(rounded_quantity) * Decimal(rounded_price)
    )

    return rounded_quantity, rounded_price, notional, symbol_info

class BinanceSpotSignedClient:
    def __init__(self, config: SpotMicroLiveConfig):
        self.config = config

    def _timestamp_ms(self) -> int:
        try:
            response = requests.get(
                f"{self.config.rest_base_url.rstrip('/')}/api/v3/time",
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return int(data["serverTime"])
        except Exception:
            return int(time.time() * 1000)

    def sanitized_config(self) -> dict[str, Any]:
        return sanitize_payload(self.config.model_dump(mode="json"))

    def _sign(self, params: dict[str, Any]) -> str:
        query = urlencode(params, doseq=True)
        return hmac.new(self.config.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()

    def signed_request(self, *, method: str, path: str, params: dict[str, Any] | None = None) -> SignedResponse:
        resolved = dict(params or {})
        resolved["recvWindow"] = self.config.recv_window
        resolved["timestamp"] = self._timestamp_ms()
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
            return (
                to_float(item.get("free"), 0.0),
                to_float(item.get("locked"), 0.0),
            )

    return 0.0, 0.0

def run_venue_availability_check(config: SpotMicroLiveConfig | None = None) -> VenueAvailabilityReport:
    resolved = config or load_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    futures_live_available = env_bool("BINANCE_FUTURES_LIVE_TRADING_ALLOWED", False)
    spot_live_available = env_bool("BINANCE_SPOT_ENABLED", True)
    futures_live_required = False
    spot_live_selected = resolved.venue == "binance_spot"

    if not spot_live_selected:
        blockers.append("binance_spot_must_be_selected_for_brazil_live")

    if not spot_live_available:
        blockers.append("binance_spot_not_available_or_not_enabled")

    if resolved.quote_asset != "BRL":
        blockers.append("quote_asset_must_be_brl_for_100_brl_mode")

    recommendations.append("Futures live deve permanecer fora do caminho crítico para operador no Brasil.")
    recommendations.append("Spot live com pares BRL é o caminho de microcapital selecionado.")
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
        jurisdiction=resolved.jurisdiction,
        quote_asset_required="BRL",
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )

def validate_dependency_report(
    path: Path,
    blocker_name: str,
    *,
    required: bool,
) -> list[str]:
    if not required:
        return []

    report = load_json(path)

    if not report:
        return [f"{blocker_name}_missing"]

    if report.get("passed") is not True:
        return [f"{blocker_name}_not_passed"]

    return [] 

def run_spot_credential_permission_check(config: SpotMicroLiveConfig | None = None) -> SpotCredentialPermissionReport:
    resolved = config or load_config()
    blockers = validate_spot_config(resolved)
    warnings: list[str] = []
    recv_window=env_int("SPOT_MICRO_LIVE_RECV_WINDOW", 5000),
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

def run_spot_brl_pair_discovery(
    config: SpotMicroLiveConfig | None = None,
) -> SpotPairDiscoveryReport:
    resolved = config or load_config()

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    pairs: list[str] = []

    try:
        pairs = get_brl_pairs(resolved)
    except requests.RequestException as exc:
        blockers.append("brl_pair_discovery_request_failed")
        warnings.append(str(exc))

    selected_available = resolved.symbol in pairs

    if not pairs:
        blockers.append("no_brl_spot_pairs_available")

    if not selected_available:
        blockers.append("selected_brl_symbol_not_available")

    recommendations.append("Usar apenas símbolos retornados como TRADING com quoteAsset=BRL.")
    recommendations.append("Se BTCBRL não estiver disponível, escolher outro par BRL retornado pela API.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return SpotPairDiscoveryReport(
        status=status,
        passed=passed,
        decision=decision,
        quote_asset=resolved.quote_asset,
        selected_symbol=resolved.symbol,
        selected_symbol_available=selected_available,
        trading_pairs_count=len(pairs),
        trading_pairs=pairs[:100],
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )

def run_spot_brl_filter_validation(
    config: SpotMicroLiveConfig | None = None,
) -> SpotFilterValidationReport:
    resolved = config or load_config()

    blockers = validate_dependency_report(
        resolved.pair_discovery_report_path,
        "pair_discovery_report",
        required=resolved.require_pair_discovery_passed,
    )

    warnings: list[str] = []
    recommendations: list[str] = []

    symbol_info: dict[str, Any] = {}
    current_price = 0.0
    rounded_quantity = "0"
    rounded_price = "0"
    notional = 0.0
    min_notional = None
    max_notional = None
    step_size = None
    min_qty = None
    tick_size = None

    try:
        rounded_quantity, rounded_price, notional, symbol_info = build_order_contract(resolved)
        current_price = get_current_price(resolved)

        filters = filters_by_type(symbol_info)
        lot_size = filters.get("LOT_SIZE", {})
        price_filter = filters.get("PRICE_FILTER", {})

        min_notional, max_notional = notional_bounds(filters)

        step_size = lot_size.get("stepSize")
        min_qty = to_float(lot_size.get("minQty"), 0.0) if lot_size else None
        tick_size = price_filter.get("tickSize")

    except (requests.RequestException, ValueError, ArithmeticError, InvalidOperation) as exc:
        blockers.append("symbol_filter_validation_request_failed")
        warnings.append(str(exc))

    if symbol_info:
        if symbol_info.get("status") != "TRADING":
            blockers.append("symbol_not_trading")

        if symbol_info.get("quoteAsset") != resolved.quote_asset:
            blockers.append("symbol_quote_asset_mismatch")

        if symbol_info.get("baseAsset") != resolved.base_asset:
            warnings.append("symbol_base_asset_differs_from_config")

    if resolved.order_quote_amount < resolved.min_order_quote_amount:
        blockers.append("order_quote_below_min_brl_limit")

    if resolved.order_quote_amount > resolved.max_order_quote_amount:
        blockers.append("order_quote_above_max_brl_limit")

    if notional < resolved.min_order_quote_amount:
        blockers.append("computed_notional_below_min_brl_limit")

    if notional > resolved.max_order_quote_amount:
        blockers.append("computed_notional_above_max_brl_limit")

    if min_notional is not None and notional < min_notional:
        blockers.append("computed_notional_below_exchange_min_notional")

    if max_notional is not None and max_notional > 0 and notional > max_notional:
        blockers.append("computed_notional_above_exchange_max_notional")

    if min_qty is not None and float(rounded_quantity or 0) < min_qty:
        blockers.append("computed_quantity_below_exchange_min_qty")

    if resolved.min_gross_profit_target_pct < 0.005:
        blockers.append("gross_profit_target_below_0_5_pct")

    recommendations.append("A ordem deve respeitar PRICE_FILTER, LOT_SIZE e MIN_NOTIONAL/NOTIONAL.")
    recommendations.append("Para capital de 100 BRL, manter notional por ordem entre 10 e 20 BRL.")
    recommendations.append("Alvo bruto >0,5% é requisito mínimo, não garantia de lucro líquido.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return SpotFilterValidationReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        status_symbol=str(symbol_info.get("status", "")),
        base_asset=str(symbol_info.get("baseAsset", "")),
        quote_asset=str(symbol_info.get("quoteAsset", "")),
        current_price=current_price,
        requested_quote_amount=resolved.order_quote_amount,
        computed_quantity=float(rounded_quantity or 0),
        rounded_quantity=rounded_quantity,
        rounded_price=rounded_price,
        resulting_notional=notional,
        min_notional=min_notional,
        max_notional=max_notional,
        step_size=step_size,
        min_qty=min_qty,
        tick_size=tick_size,
        min_gross_profit_target_pct=resolved.min_gross_profit_target_pct,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )

def run_spot_readonly_snapshot(config: SpotMicroLiveConfig | None = None) -> SpotAccountReadOnlyReport:
    resolved = config or load_config()

    blockers = (
        validate_spot_config(resolved)
        + validate_phase32(resolved)
        + validate_dependency_report(
            resolved.venue_report_path,
            "venue_report",
            required=resolved.require_venue_passed,
        )
        + validate_dependency_report(
            resolved.credential_report_path,
            "credential_report",
            required=resolved.require_credential_passed,
        )
        + validate_dependency_report(
            resolved.filter_report_path,
            "filter_validation_report",
            required=resolved.require_filter_validation_passed,
        )
    )

    warnings: list[str] = []
    recommendations: list[str] = []
    metadata: dict[str, Any] = {}

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
        open_orders = client.signed_request(
            method="GET",
            path="/api/v3/openOrders",
            params={"symbol": resolved.symbol},
        )

        if not account.ok:
            blockers.append("spot_account_request_failed")
            metadata["account_http_status"] = account.http_status
            metadata["account_error"] = account.error_message
            metadata["account_data"] = sanitize_payload(account.data)
        else:
            balances_read = True
            base_free, base_locked = extract_balance(account.data or {}, resolved.base_asset)
            quote_free, quote_locked = extract_balance(account.data or {}, resolved.quote_asset)
        if not open_orders.ok:
            blockers.append("spot_open_orders_request_failed")
            metadata["open_orders_http_status"] = open_orders.http_status
            metadata["open_orders_error"] = open_orders.error_message
            metadata["open_orders_data"] = sanitize_payload(open_orders.data)
        else:
            open_orders_read = True
            open_orders_count = len(open_orders.data or [])

        if open_orders_count > 0:
            blockers.append("spot_open_orders_detected")

    sufficient_quote = quote_free >= resolved.order_quote_amount

    if not sufficient_quote:
        warnings.append("quote_balance_below_requested_order_amount")

    recommendations.append("Spot read-only deve confirmar saldo BRL e ordens abertas sem permitir submit/cancel.")
    recommendations.append("Para BUY em BRL, quote_free precisa cobrir ordem + taxas.")
    recommendations.append("Em Spot, reconciliação usa balances BTC/BRL e open orders, não positionAmt de Futures.")

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
        sufficient_quote_for_test_order=sufficient_quote,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        metadata=metadata,
    )

def run_spot_dry_run_execution_contract(
    config: SpotMicroLiveConfig | None = None,
) -> SpotDryRunExecutionContractReport:
    resolved = config or load_config()

    blockers = (
        validate_phase32(resolved)
        + validate_dependency_report(
            resolved.readonly_report_path,
            "readonly_report",
            required=resolved.require_readonly_passed,
        )
        + validate_dependency_report(
            resolved.filter_report_path,
            "filter_validation_report",
            required=resolved.require_filter_validation_passed,
        )
    )

    warnings: list[str] = []
    recommendations: list[str] = []

    quantity = "0"
    price = "0"
    notional = 0.0

    try:
        quantity, price, notional, _ = build_order_contract(resolved)
    except (requests.RequestException, ArithmeticError, ValueError, InvalidOperation) as exc:
        blockers.append("dry_run_contract_build_failed")
        warnings.append(str(exc))

    risk_passed = True
    execution_contract_valid = True

    if resolved.side.upper() not in {"BUY", "SELL"}:
        blockers.append("invalid_spot_side")
        execution_contract_valid = False

    if float(quantity or 0) <= 0:
        blockers.append("quantity_must_be_positive")
        risk_passed = False

    if float(price or 0) <= 0:
        blockers.append("price_must_be_positive")
        risk_passed = False

    if notional < resolved.min_order_quote_amount:
        blockers.append("notional_below_min_brl_limit")
        risk_passed = False

    if notional > resolved.max_order_quote_amount:
        blockers.append("notional_above_max_brl_limit")
        risk_passed = False

    if resolved.min_gross_profit_target_pct < 0.005:
        blockers.append("gross_profit_target_below_0_5_pct")
        risk_passed = False

    recommendations.append("Dry-run Spot BRL não envia ordem; apenas valida contrato, filtros e envelope.")
    recommendations.append("Só avance para small-order após read-only e dry-run aprovados.")
    recommendations.append("A ordem real continua bloqueada por flags até liberação manual.")

    passed = not blockers and risk_passed and execution_contract_valid
    status, decision = final_status(passed, warnings)

    return SpotDryRunExecutionContractReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        side=resolved.side.upper(),
        quantity=quantity,
        price=price,
        quote_asset=resolved.quote_asset,
        notional_quote=notional,
        risk_passed=risk_passed,
        execution_contract_valid=execution_contract_valid,
        target_gross_profit_pct=resolved.min_gross_profit_target_pct,
        submitted=False,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
    )


def validate_small_order_unlock(config: SpotMicroLiveConfig) -> list[str]:
    blockers = (
        validate_spot_config(config)
        + validate_phase32(config)
        + validate_dependency_report(
            config.filter_report_path,
            "filter_validation_report",
            required=config.require_filter_validation_passed,
        )
        + validate_dependency_report(
            config.readonly_report_path,
            "readonly_report",
            required=config.require_readonly_passed,
        )
        + validate_dependency_report(
            config.dry_run_report_path,
            "dry_run_report",
            required=config.require_dry_run_passed,
        )
    )

    if not config.spot_trading_enabled_declared:
        blockers.append("spot_trading_permission_not_declared_enabled")

    if not config.allow_real_order_submission:
        blockers.append("spot_real_order_submission_not_allowed")

    if not config.allow_real_cancel:
        blockers.append("spot_real_cancel_not_allowed")

    if config.confirmation_phrase != "I_ACCEPT_SPOT_MICRO_LIVE_RISK":
        blockers.append("spot_micro_live_confirmation_phrase_required")

    if config.market_orders_allowed:
        blockers.append("market_orders_must_remain_disabled_for_first_micro_live")

    return blockers

def run_spot_small_limit_order(
    config: SpotMicroLiveConfig | None = None,
) -> SpotSmallLimitOrderReport:
    resolved = config or load_config()

    blockers = validate_small_order_unlock(resolved)
    warnings: list[str] = []
    recommendations: list[str] = []
    metadata: dict[str, Any] = {}

    quantity = "0"
    price = "0"
    notional = 0.0

    test_order_passed = False
    submitted = False
    order_id = None
    client_order_id = None
    cancel_attempted = False
    cancel_passed = False
    fill_detected = False
    rejection_detected = False
    final_reconciled = False

    try:
        quantity, price, notional, _ = build_order_contract(resolved)
    except (requests.RequestException, ArithmeticError, ValueError, InvalidOperation) as exc:
        blockers.append("small_order_contract_build_failed")
        warnings.append(str(exc))

    if notional < resolved.min_order_quote_amount:
        blockers.append("small_order_notional_below_min_brl_limit")

    if notional > resolved.max_order_quote_amount:
        blockers.append("small_order_notional_above_max_brl_limit")

    if not blockers:
        client = BinanceSpotSignedClient(resolved)
        client_order_id = f"spot_brl_micro_live_{int(time.time())}"

        params = {
            "symbol": resolved.symbol,
            "side": resolved.side.upper(),
            "type": "LIMIT",
            "quantity": quantity,
            "price": price,
            "timeInForce": "GTC",
            "newClientOrderId": client_order_id,
            "newOrderRespType": "ACK",
        }

        test_order = client.signed_request(
            method="POST",
            path="/api/v3/order/test",
            params=params,
        )

        test_order_passed = test_order.ok

        if not test_order.ok:
            blockers.append("spot_test_order_not_passed")
            metadata["test_order_http_status"] = test_order.http_status
            metadata["test_order_error"] = test_order.error_message
            metadata["test_order_data"] = sanitize_payload(test_order.data)
            metadata["test_order_params"] = sanitize_payload(params)
            recommendations.append(
                "Verificar permissões Spot Trading, saldo BRL, filtros e assinatura."
            )

        if test_order.ok:
            order = client.signed_request(
                method="POST",
                path="/api/v3/order",
                params=params,
            )

            submitted = order.ok

            if not order.ok:
                blockers.append("spot_order_submit_failed")
                rejection_detected = True
                metadata["order_http_status"] = order.http_status
                metadata["order_error"] = order.error_message
                metadata["order_data"] = sanitize_payload(order.data)

            else:
                data = order.data or {}
                order_id = data.get("orderId")

                status = str(data.get("status", "")).upper()
                executed_qty = float(data.get("executedQty", 0) or 0)
                cumulative_quote_qty = float(data.get("cummulativeQuoteQty", 0) or 0)

                metadata["submit_order_data"] = sanitize_payload(data)

                fill_detected = (
                    status in {"FILLED", "PARTIALLY_FILLED"}
                    or executed_qty > 0
                    or cumulative_quote_qty > 0
                )

                if fill_detected:
                    warnings.append("spot_order_filled_on_submit_response")
                    metadata["executed_qty"] = executed_qty
                    metadata["cummulative_quote_qty"] = cumulative_quote_qty

                cancel_attempted = True

                cancel_params = {"symbol": resolved.symbol}

                if order_id:
                    cancel_params["orderId"] = order_id
                else:
                    cancel_params["origClientOrderId"] = client_order_id

                cancel = client.signed_request(
                    method="DELETE",
                    path="/api/v3/order",
                    params=cancel_params,
                )

                cancel_passed = cancel.ok

                if not cancel.ok:
                    metadata["cancel_http_status"] = cancel.http_status
                    metadata["cancel_error"] = cancel.error_message
                    metadata["cancel_data"] = sanitize_payload(cancel.data)

                    order_status_params = {"symbol": resolved.symbol}

                    if order_id:
                        order_status_params["orderId"] = order_id
                    else:
                        order_status_params["origClientOrderId"] = client_order_id

                    order_status = client.signed_request(
                        method="GET",
                        path="/api/v3/order",
                        params=order_status_params,
                    )

                    if order_status.ok:
                        status_data = order_status.data or {}
                        order_status_value = str(status_data.get("status", "")).upper()
                        executed_qty = float(status_data.get("executedQty", 0) or 0)
                        cumulative_quote_qty = float(
                            status_data.get("cummulativeQuoteQty", 0) or 0
                        )

                        metadata["post_cancel_order_status"] = sanitize_payload(
                            status_data
                        )

                        if (
                            order_status_value in {"FILLED", "PARTIALLY_FILLED"}
                            or executed_qty > 0
                            or cumulative_quote_qty > 0
                        ):
                            fill_detected = True
                            warnings.append("spot_order_filled_before_cancel_completed")
                            metadata["executed_qty"] = executed_qty
                            metadata["cummulative_quote_qty"] = cumulative_quote_qty
                        else:
                            blockers.append("spot_order_cancel_failed")

                    else:
                        blockers.append("spot_order_cancel_failed")
                        metadata["order_status_http_status"] = order_status.http_status
                        metadata["order_status_error"] = order_status.error_message
                        metadata["order_status_data"] = sanitize_payload(
                            order_status.data
                        )

        reconciliation = run_spot_reconciliation(
            resolved,
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

    recommendations.append("Após small-order, desligar flags de submit/cancel.")
    recommendations.append("Se houver ordem aberta ou saldo locked, acionar kill switch/revisão manual.")
    recommendations.append("Primeira ordem real deve ser LIMIT, BRL, pequena e cancelável.")

    passed = not blockers
    status, decision = final_status(passed, warnings)

    return SpotSmallLimitOrderReport(
        status=status,
        passed=passed,
        decision=decision,
        symbol=resolved.symbol,
        side=resolved.side.upper(),
        quantity=quantity,
        price=price,
        quote_asset=resolved.quote_asset,
        notional_quote=notional,
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
        metadata=metadata,
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
    metadata: dict[str, Any] = {}

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

        account = client.signed_request(
            method="GET",
            path="/api/v3/account",
        )

        open_orders = client.signed_request(
            method="GET",
            path="/api/v3/openOrders",
            params={"symbol": resolved.symbol},
        )

        if not account.ok:
            blockers.append("spot_reconciliation_account_request_failed")
            metadata["account_http_status"] = account.http_status
            metadata["account_error"] = account.error_message
            metadata["account_data"] = sanitize_payload(account.data)
        else:
            base_free, base_locked = extract_balance(
                account.data or {},
                resolved.base_asset,
            )
            quote_free, quote_locked = extract_balance(
                account.data or {},
                resolved.quote_asset,
            )

        if not open_orders.ok:
            blockers.append("spot_reconciliation_open_orders_request_failed")
            metadata["open_orders_http_status"] = open_orders.http_status
            metadata["open_orders_error"] = open_orders.error_message
            metadata["open_orders_data"] = sanitize_payload(open_orders.data)
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
    recommendations.append("Fill em Spot altera saldo BTC/BRL; não existe positionAmt como em Futures.")

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
        metadata=metadata,
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
