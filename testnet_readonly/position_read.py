from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.signed_client import BinanceTestnetAdapterConfig
from testnet_readonly.account_read import read_real_testnet_account_snapshot


try:
    from binance_testnet_adapter.sanitization import sanitize_artifact_payload
except ImportError:  # pragma: no cover - fallback for older project states
    def sanitize_artifact_payload(payload: Any) -> Any:
        return payload


__test__ = False


PositionStatus = Literal["PASS", "WARN", "FAIL"]


class RealPositionSnapshotReadReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "real_testnet_position_snapshot_read"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: PositionStatus
    passed: bool
    simulated: bool

    symbol: str = "BTCUSDT"

    position_found: bool = False
    flat: bool = True
    position_amt: float = 0.0
    notional: float = 0.0
    unrealized_pnl: float = 0.0
    mark_price: float = 0.0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    position: dict[str, Any] | None = None
    account_snapshot: dict[str, Any] | None = None


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _find_position(positions: list[Any], symbol: str) -> dict[str, Any] | None:
    target = symbol.upper()

    for item in positions:
        if hasattr(item, "model_dump"):
            parsed = item.model_dump(mode="json")
        elif isinstance(item, dict):
            parsed = item
        else:
            continue

        if str(parsed.get("symbol", "")).upper() == target:
            return parsed

    return None


def read_real_testnet_position_snapshot(
    *,
    symbol: str = "BTCUSDT",
    require_flat: bool = True,
    adapter_config: BinanceTestnetAdapterConfig | None = None,
) -> RealPositionSnapshotReadReport:
    account = read_real_testnet_account_snapshot(
        symbol=symbol,
        adapter_config=adapter_config,
    )

    account_snapshot = account.account_snapshot or {}
    positions = account_snapshot.get("positions", []) or []
    position = _find_position(positions, symbol)

    warnings = list(account.warnings or [])
    blockers = list(account.blockers or [])

    position_found = position is not None

    if position is None:
        position_amt = 0.0
        notional = 0.0
        unrealized_pnl = 0.0
        mark_price = 0.0
        warnings.append("position_not_returned_for_symbol")
    else:
        position_amt = _as_float(
            position.get("positionAmt", position.get("position_amt", position.get("position_amount", 0.0)))
        )
        notional = _as_float(position.get("notional", position.get("notionalValue", 0.0)))
        unrealized_pnl = _as_float(
            position.get("unRealizedProfit", position.get("unrealizedProfit", position.get("unrealized_pnl", 0.0)))
        )
        mark_price = _as_float(position.get("markPrice", position.get("mark_price", 0.0)))

    flat = abs(position_amt) <= 1e-12 and abs(notional) <= 1e-12

    if not account.passed:
        blockers.append("account_snapshot_not_passed")

    if require_flat and not flat:
        blockers.append("position_not_flat")

    passed = len(blockers) == 0
    status: PositionStatus = "PASS" if passed and not warnings else "WARN" if passed else "FAIL"

    return RealPositionSnapshotReadReport(
        status=status,
        passed=passed,
        simulated=account.simulated,
        symbol=symbol,
        position_found=position_found,
        flat=flat,
        position_amt=position_amt,
        notional=notional,
        unrealized_pnl=unrealized_pnl,
        mark_price=mark_price,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        position=sanitize_artifact_payload(position) if position else None,
        account_snapshot=sanitize_artifact_payload(account_snapshot),
    )


def export_real_position_snapshot_read_report(
    report: RealPositionSnapshotReadReport | dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_position_snapshot_read",
) -> Path:
    path = Path(output_dir or os.getenv("TESTNET_READONLY_OUTPUT_DIR", "artifacts/testnet_readonly"))
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"

    data = report.model_dump(mode="json") if hasattr(report, "model_dump") else report
    data = sanitize_artifact_payload(data)

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path
