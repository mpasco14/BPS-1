from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


ReconciliationStatus = Literal["PASS", "WARN", "FAIL"]


class TestnetPortfolioReconciliationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_readiness")

    max_position_qty_diff: float = 0.000001
    max_notional_diff_usd: float = 1.0
    require_flat_after_test: bool = True


class TestnetPositionSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    side: str = "FLAT"
    quantity: float = 0.0
    entry_price: float | None = None
    mark_price: float | None = None
    notional_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestnetPortfolioReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "testnet_portfolio_reconciliation"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ReconciliationStatus
    passed: bool

    symbol: str
    qty_diff: float
    notional_diff_usd: float
    local_flat: bool
    exchange_flat: bool

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    local_position: dict[str, Any]
    exchange_position: dict[str, Any]
    config: dict[str, Any]


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


def load_testnet_portfolio_reconciliation_config() -> TestnetPortfolioReconciliationConfig:
    return TestnetPortfolioReconciliationConfig(
        output_dir=Path(os.getenv("TESTNET_PORTFOLIO_RECON_OUTPUT_DIR", "artifacts/testnet_readiness")),
        max_position_qty_diff=env_float("TESTNET_PORTFOLIO_MAX_POSITION_QTY_DIFF", 0.000001),
        max_notional_diff_usd=env_float("TESTNET_PORTFOLIO_MAX_NOTIONAL_DIFF_USD", 1.0),
        require_flat_after_test=env_bool("TESTNET_PORTFOLIO_REQUIRE_FLAT_AFTER_TEST", True),
    )


def position_is_flat(position: TestnetPositionSnapshot) -> bool:
    return abs(position.quantity) <= 1e-12 or position.side == "FLAT"


def reconcile_testnet_portfolio(
    *,
    local_position: TestnetPositionSnapshot | dict[str, Any],
    exchange_position: TestnetPositionSnapshot | dict[str, Any],
    config: TestnetPortfolioReconciliationConfig | None = None,
) -> TestnetPortfolioReconciliationReport:
    resolved_config = config or load_testnet_portfolio_reconciliation_config()
    local = local_position if isinstance(local_position, TestnetPositionSnapshot) else TestnetPositionSnapshot.model_validate(local_position)
    exchange = exchange_position if isinstance(exchange_position, TestnetPositionSnapshot) else TestnetPositionSnapshot.model_validate(exchange_position)

    blockers: list[str] = []
    warnings: list[str] = []

    if local.symbol != exchange.symbol:
        blockers.append("symbol_mismatch")

    if local.side != exchange.side:
        blockers.append("side_mismatch")

    qty_diff = abs(local.quantity - exchange.quantity)
    notional_diff = abs(local.notional_usd - exchange.notional_usd)

    if qty_diff > resolved_config.max_position_qty_diff:
        blockers.append("position_qty_diff_above_limit")

    if notional_diff > resolved_config.max_notional_diff_usd:
        blockers.append("notional_diff_above_limit")

    local_flat = position_is_flat(local)
    exchange_flat = position_is_flat(exchange)

    if resolved_config.require_flat_after_test:
        if not local_flat:
            blockers.append("local_position_not_flat_after_test")
        if not exchange_flat:
            blockers.append("exchange_position_not_flat_after_test")

    if local.unrealized_pnl_usd != exchange.unrealized_pnl_usd:
        warnings.append("unrealized_pnl_diff_detected")

    passed = not blockers

    return TestnetPortfolioReconciliationReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        symbol=local.symbol,
        qty_diff=round(qty_diff, 12),
        notional_diff_usd=round(notional_diff, 8),
        local_flat=local_flat,
        exchange_flat=exchange_flat,
        blockers=blockers,
        warnings=warnings,
        local_position=local.model_dump(mode="json"),
        exchange_position=exchange.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def build_flat_position(symbol: str = "BTCUSDT") -> TestnetPositionSnapshot:
    return TestnetPositionSnapshot(
        symbol=symbol,
        side="FLAT",
        quantity=0.0,
        notional_usd=0.0,
        unrealized_pnl_usd=0.0,
    )


def export_testnet_portfolio_reconciliation_report(
    report: TestnetPortfolioReconciliationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "testnet_portfolio_reconciliation_report",
) -> Path:
    config = load_testnet_portfolio_reconciliation_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path