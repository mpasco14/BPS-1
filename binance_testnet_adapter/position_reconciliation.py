from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.account_snapshot import (
    BinanceTestnetAccountSnapshotReport,
    BinanceTestnetPositionSnapshot,
)
from testnet_readiness.testnet_portfolio_reconciliation import (
    TestnetPositionSnapshot,
    reconcile_testnet_portfolio,
)


PositionReconStatus = Literal["PASS", "WARN", "FAIL"]


class BinanceTestnetPositionReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_testnet_position_reconciliation_adapter"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: PositionReconStatus
    passed: bool

    symbol: str

    local_position: dict[str, Any]
    exchange_position: dict[str, Any]
    portfolio_reconciliation: dict[str, Any]

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def infer_side_from_position_amt(position_amt: float) -> str:
    if position_amt > 0:
        return "LONG"

    if position_amt < 0:
        return "SHORT"

    return "FLAT"


def convert_binance_position_to_testnet_position(
    *,
    position: BinanceTestnetPositionSnapshot | dict[str, Any],
) -> TestnetPositionSnapshot:
    parsed = (
        position
        if isinstance(position, BinanceTestnetPositionSnapshot)
        else BinanceTestnetPositionSnapshot.model_validate(position)
    )

    return TestnetPositionSnapshot(
        symbol=parsed.symbol,
        side=infer_side_from_position_amt(parsed.position_amt),
        quantity=abs(parsed.position_amt),
        entry_price=parsed.entry_price,
        mark_price=parsed.mark_price,
        notional_usd=abs(parsed.notional),
        unrealized_pnl_usd=parsed.unrealized_pnl,
        metadata={
            "position_side": parsed.position_side,
            "update_time": parsed.update_time,
        },
    )


def find_exchange_position(
    *,
    account_snapshot: BinanceTestnetAccountSnapshotReport | dict[str, Any],
    symbol: str,
) -> TestnetPositionSnapshot:
    parsed = (
        account_snapshot
        if isinstance(account_snapshot, BinanceTestnetAccountSnapshotReport)
        else BinanceTestnetAccountSnapshotReport.model_validate(account_snapshot)
    )

    for position in parsed.positions:
        candidate = BinanceTestnetPositionSnapshot.model_validate(position)

        if candidate.symbol == symbol:
            return convert_binance_position_to_testnet_position(position=candidate)

    return TestnetPositionSnapshot(
        symbol=symbol,
        side="FLAT",
        quantity=0.0,
        notional_usd=0.0,
        unrealized_pnl_usd=0.0,
    )


def reconcile_binance_testnet_position(
    *,
    local_position: TestnetPositionSnapshot | dict[str, Any],
    account_snapshot: BinanceTestnetAccountSnapshotReport | dict[str, Any],
    symbol: str = "BTCUSDT",
) -> BinanceTestnetPositionReconciliationReport:
    parsed_local = (
        local_position
        if isinstance(local_position, TestnetPositionSnapshot)
        else TestnetPositionSnapshot.model_validate(local_position)
    )
    exchange_position = find_exchange_position(
        account_snapshot=account_snapshot,
        symbol=symbol,
    )

    portfolio_report = reconcile_testnet_portfolio(
        local_position=parsed_local,
        exchange_position=exchange_position,
    )

    blockers = list(portfolio_report.blockers)
    warnings = list(portfolio_report.warnings)

    return BinanceTestnetPositionReconciliationReport(
        status="PASS" if portfolio_report.passed and not warnings else "WARN" if portfolio_report.passed else "FAIL",
        passed=portfolio_report.passed,
        symbol=symbol,
        local_position=parsed_local.model_dump(mode="json"),
        exchange_position=exchange_position.model_dump(mode="json"),
        portfolio_reconciliation=portfolio_report.model_dump(mode="json"),
        blockers=blockers,
        warnings=warnings,
    )


def export_binance_testnet_position_reconciliation_report(
    report: BinanceTestnetPositionReconciliationReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "binance_testnet_position_reconciliation",
) -> Path:
    path = Path(output_dir or os.getenv("BINANCE_TESTNET_POSITION_RECON_OUTPUT_DIR", "artifacts/binance_testnet_adapter"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path