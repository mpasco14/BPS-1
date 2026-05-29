from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.account_snapshot import (
    BinanceTestnetAccountSnapshotReport,
    fetch_binance_testnet_account_snapshot,
)
from binance_testnet_adapter.signed_client import (
    BinanceTestnetAdapterConfig,
    BinanceTestnetSignedClient,
)


AccountReadStatus = Literal["PASS", "WARN", "FAIL"]


class RealAccountSnapshotReadReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "real_testnet_account_snapshot_read"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: AccountReadStatus
    passed: bool
    simulated: bool

    symbol: str

    wallet_balance: float = 0.0
    margin_balance: float = 0.0
    unrealized_profit: float = 0.0
    positions_count: int = 0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    account_snapshot: dict[str, Any]


def read_real_testnet_account_snapshot(
    *,
    symbol: str = "BTCUSDT",
    client: BinanceTestnetSignedClient | None = None,
    adapter_config: BinanceTestnetAdapterConfig | None = None,
) -> RealAccountSnapshotReadReport:
    snapshot = fetch_binance_testnet_account_snapshot(
        symbol=symbol,
        client=client,
    )

    blockers: list[str] = []
    warnings: list[str] = []

    if not snapshot.passed:
        blockers.append("account_snapshot_adapter_not_passed")
        blockers.extend(snapshot.blockers)

    warnings.extend(snapshot.warnings)

    if snapshot.total_wallet_balance < 0:
        blockers.append("wallet_balance_negative")

    if snapshot.total_margin_balance < 0:
        blockers.append("margin_balance_negative")

    if not snapshot.positions:
        warnings.append("positions_empty")

    passed = not blockers

    return RealAccountSnapshotReadReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        simulated=snapshot.simulated,
        symbol=symbol,
        wallet_balance=snapshot.total_wallet_balance,
        margin_balance=snapshot.total_margin_balance,
        unrealized_profit=snapshot.total_unrealized_profit,
        positions_count=len(snapshot.positions),
        blockers=blockers,
        warnings=sorted(set(warnings)),
        account_snapshot=snapshot.model_dump(mode="json"),
    )


def export_real_testnet_account_snapshot_read_report(
    report: RealAccountSnapshotReadReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_account_snapshot_read",
) -> Path:
    path = Path(output_dir or os.getenv("TESTNET_READONLY_ACCOUNT_OUTPUT_DIR", "artifacts/testnet_readonly"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path