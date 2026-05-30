from __future__ import annotations

import json
import os
import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from binance_testnet_adapter.signed_client import (
    BinanceTestnetAdapterConfig,
    load_binance_testnet_adapter_config,
)

try:
    from binance_testnet_adapter.sanitization import sanitize_artifact_payload
except ImportError:  # pragma: no cover - fallback for older project states
    def sanitize_artifact_payload(payload: Any) -> Any:
        return payload


__test__ = False


ReadStatus = Literal["PASS", "WARN", "FAIL"]


class RealAccountSnapshotReadReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "real_testnet_account_snapshot_read"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ReadStatus
    passed: bool
    simulated: bool

    symbol: str = "BTCUSDT"

    wallet_balance: float = 0.0
    margin_balance: float = 0.0
    unrealized_profit: float = 0.0
    positions_count: int = 0

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    account_snapshot: dict[str, Any] | None = None


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    return {}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)

    return getattr(value, key, default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _find_account_snapshot_callable() -> Any:
    """
    Locate the project-specific Binance testnet account snapshot function.

    This avoids hardcoding a function name that may differ between project phases.
    """
    import binance_testnet_adapter.account_snapshot as account_snapshot_module

    preferred_names = [
        "read_binance_testnet_account_snapshot",
        "read_binance_testnet_account_snapshot_adapter",
        "build_binance_testnet_account_snapshot",
        "build_binance_testnet_account_snapshot_report",
        "get_binance_testnet_account_snapshot",
        "fetch_binance_testnet_account_snapshot",
        "collect_binance_testnet_account_snapshot",
        "read_account_snapshot",
        "build_account_snapshot",
    ]

    for name in preferred_names:
        candidate = getattr(account_snapshot_module, name, None)

        if callable(candidate):
            return candidate

    discovered = []

    for name in dir(account_snapshot_module):
        if name.startswith("_"):
            continue

        candidate = getattr(account_snapshot_module, name)

        if not callable(candidate):
            continue

        lowered = name.lower()

        if "account" in lowered and "snapshot" in lowered:
            discovered.append(name)
            return candidate

    raise ImportError(
        "No account snapshot callable found in binance_testnet_adapter.account_snapshot. "
        f"Discovered callable names containing account/snapshot: {discovered}"
    )


def _call_account_snapshot_adapter(
    *,
    symbol: str,
    adapter_config: BinanceTestnetAdapterConfig | None = None,
) -> Any:
    """
    Calls the lower-level Binance account snapshot adapter while preserving the
    explicit adapter_config passed by tests or scripts.

    This avoids unit tests accidentally using the real .env testnet credentials.
    """
    account_snapshot_callable = _find_account_snapshot_callable()

    signature = inspect.signature(account_snapshot_callable)
    kwargs: dict[str, Any] = {}

    if "symbol" in signature.parameters:
        kwargs["symbol"] = symbol

    if adapter_config is not None:
        if "adapter_config" in signature.parameters:
            kwargs["adapter_config"] = adapter_config
        elif "config" in signature.parameters:
            kwargs["config"] = adapter_config
        elif "adapter" in signature.parameters:
            kwargs["adapter"] = adapter_config

    return account_snapshot_callable(**kwargs)

def _build_simulated_account_snapshot_report(
    *,
    symbol: str,
) -> RealAccountSnapshotReadReport:
    snapshot = {
        "source": "binance_testnet_account_snapshot_adapter",
        "status": "PASS",
        "passed": True,
        "simulated": True,
        "symbol": symbol,
        "total_wallet_balance": 5000.0,
        "total_margin_balance": 5000.0,
        "total_unrealized_profit": 0.0,
        "usdt_balance": {
            "asset": "USDT",
            "balance": 5000.0,
            "available_balance": 5000.0,
            "cross_wallet_balance": 5000.0,
            "cross_unrealized_pnl": 0.0,
        },
        "positions": [],
        "blockers": [],
        "warnings": [],
        "raw_account": {},
        "raw_balance": [],
        "raw_positions": [],
    }

    return RealAccountSnapshotReadReport(
        status="WARN",
        passed=True,
        simulated=True,
        symbol=symbol,
        wallet_balance=5000.0,
        margin_balance=5000.0,
        unrealized_profit=0.0,
        positions_count=0,
        blockers=[],
        warnings=["positions_empty"],
        account_snapshot=snapshot,
    )

def read_real_testnet_account_snapshot(
    *,
    symbol: str = "BTCUSDT",
    adapter_config: BinanceTestnetAdapterConfig | None = None,
) -> RealAccountSnapshotReadReport:
    resolved_adapter_config = adapter_config or load_binance_testnet_adapter_config()

    if resolved_adapter_config.simulate:
        return _build_simulated_account_snapshot_report(symbol=symbol)

    snapshot = _call_account_snapshot_adapter(
        symbol=symbol,
        adapter_config=resolved_adapter_config,
    )
    
    snapshot_dict = sanitize_artifact_payload(_to_dict(snapshot))

    adapter_passed = bool(_get(snapshot, "passed", False))
    simulated = bool(_get(snapshot, "simulated", False))

    blockers = list(_get(snapshot, "blockers", []) or [])
    warnings = list(_get(snapshot, "warnings", []) or [])

    positions = _get(snapshot, "positions", []) or []
    positions_count = len(positions)

    if positions_count == 0:
        warnings.append("positions_empty")

    usdt_balance = _get(snapshot, "usdt_balance", None) or {}

    wallet_balance = _as_float(_get(snapshot, "total_wallet_balance", None))
    margin_balance = _as_float(_get(snapshot, "total_margin_balance", None))
    unrealized_profit = _as_float(_get(snapshot, "total_unrealized_profit", None))

    if isinstance(usdt_balance, dict):
        wallet_balance = _as_float(usdt_balance.get("balance"), wallet_balance)
        margin_balance = _as_float(usdt_balance.get("available_balance"), margin_balance)

    if not adapter_passed:
        blockers.append("account_snapshot_adapter_not_passed")

        for item in ("account_request_failed", "balance_request_failed", "position_request_failed"):
            if item not in blockers and item in (list(_get(snapshot, "blockers", []) or [])):
                blockers.append(item)

    passed = len(blockers) == 0
    status: ReadStatus = "PASS" if passed and not warnings else "WARN" if passed else "FAIL"

    return RealAccountSnapshotReadReport(
        status=status,
        passed=passed,
        simulated=simulated,
        symbol=symbol,
        wallet_balance=wallet_balance,
        margin_balance=margin_balance,
        unrealized_profit=unrealized_profit,
        positions_count=positions_count,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        account_snapshot=snapshot_dict,
    )


def export_real_account_snapshot_read_report(
    report: RealAccountSnapshotReadReport | dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_account_snapshot_read",
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
