from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


DataQualityStatus = Literal["PASS", "WARN", "FAIL"]


class DataQualityConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/governance")

    max_candle_age_seconds: float = 120
    max_orderbook_age_seconds: float = 15
    max_spread_pct: float = 0.002
    min_liquidity_usd: float = 50_000
    max_price_divergence_pct: float = 0.005

    require_websocket_connected: bool = True
    require_orderbook_tradeable: bool = True
    block_on_missing_features: bool = True
    block_on_nan: bool = True


class DataQualityInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    symbol: str = "BTCUSDT"
    timeframe: str | None = None

    candle_timestamp: datetime | None = None
    orderbook_timestamp: datetime | None = None

    last_price: float | None = None
    reference_price: float | None = None

    spread_pct: float | None = None
    liquidity_usd: float | None = None

    websocket_connected: bool = True
    orderbook_tradeable: bool = True

    missing_features: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    feature_values: dict[str, Any] = Field(default_factory=dict)


class DataQualityCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    status: DataQualityStatus
    title: str
    message: str

    value: Any | None = None
    expected: Any | None = None
    blocking: bool = False


class DataQualityReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "data_quality_gate"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    passed: bool
    status: str

    symbol: str
    timeframe: str | None = None

    checks_count: int
    pass_count: int
    warn_count: int
    fail_count: int
    blocking_fail_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)


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


def load_data_quality_config() -> DataQualityConfig:
    return DataQualityConfig(
        output_dir=Path(os.getenv("DATA_QUALITY_OUTPUT_DIR", "artifacts/governance")),
        max_candle_age_seconds=env_float("DATA_QUALITY_MAX_CANDLE_AGE_SECONDS", 120),
        max_orderbook_age_seconds=env_float("DATA_QUALITY_MAX_ORDERBOOK_AGE_SECONDS", 15),
        max_spread_pct=env_float("DATA_QUALITY_MAX_SPREAD_PCT", 0.002),
        min_liquidity_usd=env_float("DATA_QUALITY_MIN_LIQUIDITY_USD", 50_000),
        max_price_divergence_pct=env_float("DATA_QUALITY_MAX_PRICE_DIVERGENCE_PCT", 0.005),
        require_websocket_connected=env_bool("DATA_QUALITY_REQUIRE_WEBSOCKET_CONNECTED", True),
        require_orderbook_tradeable=env_bool("DATA_QUALITY_REQUIRE_ORDERBOOK_TRADEABLE", True),
        block_on_missing_features=env_bool("DATA_QUALITY_BLOCK_ON_MISSING_FEATURES", True),
        block_on_nan=env_bool("DATA_QUALITY_BLOCK_ON_NAN", True),
    )


def seconds_between(now: datetime, then: datetime | None) -> float | None:
    if then is None:
        return None

    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return abs((now - then).total_seconds())


def has_nan_values(values: dict[str, Any]) -> list[str]:
    invalid: list[str] = []

    for key, value in values.items():
        if isinstance(value, float) and math.isnan(value):
            invalid.append(key)
        elif value is None:
            invalid.append(key)

    return invalid


def price_divergence_pct(last_price: float | None, reference_price: float | None) -> float | None:
    if last_price is None or reference_price is None or reference_price == 0:
        return None

    return abs(last_price - reference_price) / abs(reference_price)


def make_check(
    *,
    code: str,
    status: DataQualityStatus,
    title: str,
    message: str,
    value: Any | None = None,
    expected: Any | None = None,
    blocking: bool = False,
) -> DataQualityCheck:
    return DataQualityCheck(
        code=code,
        status=status,
        title=title,
        message=message,
        value=value,
        expected=expected,
        blocking=blocking,
    )


def evaluate_data_quality(
    *,
    data: DataQualityInput | dict[str, Any],
    config: DataQualityConfig | None = None,
) -> DataQualityReport:
    resolved_config = config or load_data_quality_config()
    resolved_data = data if isinstance(data, DataQualityInput) else DataQualityInput.model_validate(data)

    checks: list[DataQualityCheck] = []

    candle_age = seconds_between(resolved_data.now, resolved_data.candle_timestamp)
    orderbook_age = seconds_between(resolved_data.now, resolved_data.orderbook_timestamp)
    divergence = price_divergence_pct(resolved_data.last_price, resolved_data.reference_price)
    nan_features = has_nan_values(resolved_data.feature_values)

    candle_ok = candle_age is not None and candle_age <= resolved_config.max_candle_age_seconds
    orderbook_ok = orderbook_age is not None and orderbook_age <= resolved_config.max_orderbook_age_seconds
    spread_ok = resolved_data.spread_pct is not None and resolved_data.spread_pct <= resolved_config.max_spread_pct
    liquidity_ok = resolved_data.liquidity_usd is not None and resolved_data.liquidity_usd >= resolved_config.min_liquidity_usd
    divergence_ok = divergence is not None and divergence <= resolved_config.max_price_divergence_pct

    checks.append(
        make_check(
            code="CANDLE_FRESH" if candle_ok else "CANDLE_STALE_OR_MISSING",
            status="PASS" if candle_ok else "FAIL",
            title="Candle freshness",
            message="Valida se o candle usado nas features é recente.",
            value=candle_age,
            expected=f"<={resolved_config.max_candle_age_seconds}",
            blocking=not candle_ok,
        )
    )

    checks.append(
        make_check(
            code="ORDERBOOK_FRESH" if orderbook_ok else "ORDERBOOK_STALE_OR_MISSING",
            status="PASS" if orderbook_ok else "FAIL",
            title="Orderbook freshness",
            message="Valida se o orderbook usado está recente.",
            value=orderbook_age,
            expected=f"<={resolved_config.max_orderbook_age_seconds}",
            blocking=not orderbook_ok,
        )
    )

    checks.append(
        make_check(
            code="SPREAD_OK" if spread_ok else "SPREAD_TOO_HIGH_OR_MISSING",
            status="PASS" if spread_ok else "FAIL",
            title="Spread",
            message="Valida spread máximo permitido.",
            value=resolved_data.spread_pct,
            expected=f"<={resolved_config.max_spread_pct}",
            blocking=not spread_ok,
        )
    )

    checks.append(
        make_check(
            code="LIQUIDITY_OK" if liquidity_ok else "LIQUIDITY_LOW_OR_MISSING",
            status="PASS" if liquidity_ok else "FAIL",
            title="Liquidity",
            message="Valida liquidez mínima.",
            value=resolved_data.liquidity_usd,
            expected=f">={resolved_config.min_liquidity_usd}",
            blocking=not liquidity_ok,
        )
    )

    checks.append(
        make_check(
            code="PRICE_DIVERGENCE_OK" if divergence_ok else "PRICE_DIVERGENCE_HIGH_OR_MISSING",
            status="PASS" if divergence_ok else "FAIL",
            title="Price divergence",
            message="Valida divergência entre preço principal e referência.",
            value=divergence,
            expected=f"<={resolved_config.max_price_divergence_pct}",
            blocking=not divergence_ok,
        )
    )

    if resolved_config.require_websocket_connected:
        checks.append(
            make_check(
                code="WEBSOCKET_CONNECTED" if resolved_data.websocket_connected else "WEBSOCKET_DISCONNECTED",
                status="PASS" if resolved_data.websocket_connected else "FAIL",
                title="WebSocket",
                message="Valida conexão WebSocket.",
                value=resolved_data.websocket_connected,
                expected=True,
                blocking=not resolved_data.websocket_connected,
            )
        )

    if resolved_config.require_orderbook_tradeable:
        checks.append(
            make_check(
                code="ORDERBOOK_TRADEABLE" if resolved_data.orderbook_tradeable else "ORDERBOOK_NOT_TRADEABLE",
                status="PASS" if resolved_data.orderbook_tradeable else "FAIL",
                title="Orderbook tradeable",
                message="Valida se o orderbook permite operação.",
                value=resolved_data.orderbook_tradeable,
                expected=True,
                blocking=not resolved_data.orderbook_tradeable,
            )
        )

    if resolved_data.missing_features:
        checks.append(
            make_check(
                code="MISSING_FEATURES",
                status="FAIL" if resolved_config.block_on_missing_features else "WARN",
                title="Missing features",
                message="Existem features ausentes.",
                value=resolved_data.missing_features,
                expected=[],
                blocking=resolved_config.block_on_missing_features,
            )
        )
    else:
        checks.append(
            make_check(
                code="NO_MISSING_FEATURES",
                status="PASS",
                title="No missing features",
                message="Nenhuma feature obrigatória ausente.",
                value=[],
                expected=[],
            )
        )

    if nan_features:
        checks.append(
            make_check(
                code="NAN_FEATURES",
                status="FAIL" if resolved_config.block_on_nan else "WARN",
                title="NaN features",
                message="Existem features inválidas ou NaN.",
                value=nan_features,
                expected=[],
                blocking=resolved_config.block_on_nan,
            )
        )
    else:
        checks.append(
            make_check(
                code="NO_NAN_FEATURES",
                status="PASS",
                title="No NaN features",
                message="Nenhuma feature inválida ou NaN.",
                value=[],
                expected=[],
            )
        )

    pass_count = sum(1 for item in checks if item.status == "PASS")
    warn_count = sum(1 for item in checks if item.status == "WARN")
    fail_count = sum(1 for item in checks if item.status == "FAIL")
    blocking_fail_count = sum(1 for item in checks if item.status == "FAIL" and item.blocking)

    blockers = [item.code for item in checks if item.status == "FAIL" and item.blocking]
    warnings = [item.code for item in checks if item.status == "WARN"]

    passed = blocking_fail_count == 0

    return DataQualityReport(
        passed=passed,
        status="PASS" if passed else "FAIL",
        symbol=resolved_data.symbol,
        timeframe=resolved_data.timeframe,
        checks_count=len(checks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        blocking_fail_count=blocking_fail_count,
        blockers=blockers,
        warnings=warnings,
        checks=[item.model_dump(mode="json") for item in checks],
    )


def export_data_quality_report(
    report: DataQualityReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "data_quality_latest",
) -> Path:
    config = load_data_quality_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    safe_name = name.replace("/", "_").replace("\\", "_")
    output_path = path / f"{safe_name}.json"

    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path