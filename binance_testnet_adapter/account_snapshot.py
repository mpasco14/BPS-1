from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.signed_client import (
    BinanceSignedResponse,
    BinanceTestnetSignedClient,
    build_binance_testnet_signed_client,
)


AccountSnapshotStatus = Literal["PASS", "WARN", "FAIL"]


class BinanceTestnetBalanceSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset: str = "USDT"
    balance: float = 0.0
    available_balance: float = 0.0
    cross_wallet_balance: float = 0.0
    cross_unrealized_pnl: float = 0.0


class BinanceTestnetPositionSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str = "BTCUSDT"
    position_side: str = "BOTH"
    position_amt: float = 0.0
    entry_price: float = 0.0
    mark_price: float = 0.0
    unrealized_pnl: float = 0.0
    notional: float = 0.0
    update_time: int | None = None


class BinanceTestnetAccountSnapshotReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "binance_testnet_account_snapshot_adapter"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: AccountSnapshotStatus
    passed: bool
    simulated: bool

    symbol: str = "BTCUSDT"

    total_wallet_balance: float = 0.0
    total_margin_balance: float = 0.0
    total_unrealized_profit: float = 0.0

    usdt_balance: dict[str, Any] | None = None
    positions: list[dict[str, Any]] = Field(default_factory=list)

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    raw_account: Any = None
    raw_balance: Any = None
    raw_positions: Any = None


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_usdt_balance(balance_payload: Any) -> BinanceTestnetBalanceSnapshot | None:
    if not isinstance(balance_payload, list):
        return None

    for item in balance_payload:
        if item.get("asset") == "USDT":
            return BinanceTestnetBalanceSnapshot(
                asset="USDT",
                balance=to_float(item.get("balance")),
                available_balance=to_float(item.get("availableBalance")),
                cross_wallet_balance=to_float(item.get("crossWalletBalance")),
                cross_unrealized_pnl=to_float(item.get("crossUnPnl")),
            )

    return None


def parse_positions(position_payload: Any) -> list[BinanceTestnetPositionSnapshot]:
    if not isinstance(position_payload, list):
        return []

    positions: list[BinanceTestnetPositionSnapshot] = []

    for item in position_payload:
        positions.append(
            BinanceTestnetPositionSnapshot(
                symbol=item.get("symbol", "BTCUSDT"),
                position_side=item.get("positionSide", "BOTH"),
                position_amt=to_float(item.get("positionAmt")),
                entry_price=to_float(item.get("entryPrice")),
                mark_price=to_float(item.get("markPrice")),
                unrealized_pnl=to_float(item.get("unRealizedProfit")),
                notional=to_float(item.get("notional")),
                update_time=item.get("updateTime"),
            )
        )

    return positions


def simulated_account_payload() -> dict[str, Any]:
    return {
        "totalWalletBalance": "1000.00000000",
        "totalMarginBalance": "1000.00000000",
        "totalUnrealizedProfit": "0.00000000",
    }


def simulated_balance_payload() -> list[dict[str, Any]]:
    return [
        {
            "asset": "USDT",
            "balance": "1000.00000000",
            "availableBalance": "1000.00000000",
            "crossWalletBalance": "1000.00000000",
            "crossUnPnl": "0.00000000",
        }
    ]


def simulated_position_payload(symbol: str = "BTCUSDT") -> list[dict[str, Any]]:
    return [
        {
            "symbol": symbol,
            "positionSide": "BOTH",
            "positionAmt": "0",
            "entryPrice": "0",
            "markPrice": "60000",
            "unRealizedProfit": "0",
            "notional": "0",
            "updateTime": 0,
        }
    ]


def fetch_binance_testnet_account_snapshot(
    *,
    symbol: str = "BTCUSDT",
    client: BinanceTestnetSignedClient | None = None,
) -> BinanceTestnetAccountSnapshotReport:
    resolved_client = client or build_binance_testnet_signed_client()

    account_response = resolved_client.request(
        method="GET",
        path="/fapi/v3/account",
        params={},
        signed=True,
        simulate_data=simulated_account_payload(),
    )
    balance_response = resolved_client.request(
        method="GET",
        path="/fapi/v2/balance",
        params={},
        signed=True,
        simulate_data=simulated_balance_payload(),
    )
    position_response = resolved_client.request(
        method="GET",
        path="/fapi/v3/positionRisk",
        params={"symbol": symbol},
        signed=True,
        simulate_data=simulated_position_payload(symbol),
    )

    blockers: list[str] = []
    warnings: list[str] = []

    for name, response in {
        "account": account_response,
        "balance": balance_response,
        "position": position_response,
    }.items():
        if not response.ok:
            blockers.append(f"{name}_request_failed")
            if response.error_message:
                warnings.append(f"{name}:{response.error_message}")

    account_data = account_response.data or {}
    balance_data = balance_response.data or []
    position_data = position_response.data or []

    usdt_balance = parse_usdt_balance(balance_data)
    positions = parse_positions(position_data)

    if usdt_balance is None:
        warnings.append("usdt_balance_not_found")

    passed = not blockers
    simulated = account_response.simulated or balance_response.simulated or position_response.simulated

    return BinanceTestnetAccountSnapshotReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        simulated=simulated,
        symbol=symbol,
        total_wallet_balance=to_float(account_data.get("totalWalletBalance")),
        total_margin_balance=to_float(account_data.get("totalMarginBalance")),
        total_unrealized_profit=to_float(account_data.get("totalUnrealizedProfit")),
        usdt_balance=usdt_balance.model_dump(mode="json") if usdt_balance else None,
        positions=[item.model_dump(mode="json") for item in positions],
        blockers=blockers,
        warnings=warnings,
        raw_account=account_data,
        raw_balance=balance_data,
        raw_positions=position_data,
    )


def export_binance_testnet_account_snapshot(
    report: BinanceTestnetAccountSnapshotReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "binance_testnet_account_snapshot",
) -> Path:
    path = Path(output_dir or os.getenv("BINANCE_TESTNET_ACCOUNT_OUTPUT_DIR", "artifacts/binance_testnet_adapter"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path