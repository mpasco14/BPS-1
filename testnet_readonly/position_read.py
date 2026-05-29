from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.account_snapshot import (
    BinanceTestnetPositionSnapshot,
    fetch_binance_testnet_account_snapshot,
)


PositionReadStatus = Literal["PASS", "WARN", "FAIL"]


class RealPositionSnapshotReadReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "real_testnet_position_snapshot_read"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: PositionReadStatus
    passed: bool
    simulated: bool

    symbol: str
    position_found: bool
    flat: bool

    position_amt: float = 0.0
    notional: float = 0.0
    unrealized_pnl: float = 0.0
    mark_price: float = 0.0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    position: dict[str, Any] | None = None
    account_snapshot: dict[str, Any]


def find_position_from_account_snapshot(
    *,
    positions: list[dict[str, Any]],
    symbol: str,
) -> BinanceTestnetPositionSnapshot | None:
    for item in positions:
        position = BinanceTestnetPositionSnapshot.model_validate(item)
        if position.symbol == symbol:
            return position

    return None


def read_real_testnet_position_snapshot(
    *,
    symbol: str = "BTCUSDT",
    require_flat: bool | None = None,
) -> RealPositionSnapshotReadReport:
    require_final_flat = (
        os.getenv("TESTNET_READONLY_REQUIRE_FINAL_FLAT", "true").strip().lower()
        in {"1", "true", "yes", "y", "on"}
        if require_flat is None
        else require_flat
    )

    snapshot = fetch_binance_testnet_account_snapshot(symbol=symbol)
    position = find_position_from_account_snapshot(
        positions=snapshot.positions,
        symbol=symbol,
    )

    blockers: list[str] = []
    warnings: list[str] = []

    if not snapshot.passed:
        blockers.append("account_snapshot_not_passed")
        blockers.extend(snapshot.blockers)

    position_found = position is not None

    if position is None:
        warnings.append("position_not_returned_for_symbol")
        position_amt = 0.0
        notional = 0.0
        unrealized_pnl = 0.0
        mark_price = 0.0
        flat = True
    else:
        position_amt = position.position_amt
        notional = position.notional
        unrealized_pnl = position.unrealized_pnl
        mark_price = position.mark_price
        flat = abs(position_amt) <= 1e-12 and abs(notional) <= 1e-9

    if require_final_flat and not flat:
        blockers.append("position_not_flat_during_readonly_validation")

    passed = not blockers

    return RealPositionSnapshotReadReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        simulated=snapshot.simulated,
        symbol=symbol,
        position_found=position_found,
        flat=flat,
        position_amt=position_amt,
        notional=notional,
        unrealized_pnl=unrealized_pnl,
        mark_price=mark_price,
        blockers=blockers,
        warnings=sorted(set(warnings)),
        position=position.model_dump(mode="json") if position else None,
        account_snapshot=snapshot.model_dump(mode="json"),
    )


def export_real_testnet_position_snapshot_read_report(
    report: RealPositionSnapshotReadReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_position_snapshot_read",
) -> Path:
    path = Path(output_dir or os.getenv("TESTNET_READONLY_POSITION_OUTPUT_DIR", "artifacts/testnet_readonly"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path