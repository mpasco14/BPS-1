from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from testnet_readonly.account_read import RealAccountSnapshotReadReport, read_real_testnet_account_snapshot
from testnet_readonly.credential_check import (
    RealTestnetCredentialCheckConfig,
    RealTestnetCredentialCheckReport,
    evaluate_real_testnet_credential_check,
)
from testnet_readonly.open_orders_read import RealOpenOrdersReadReport, read_real_testnet_open_orders
from testnet_readonly.position_read import RealPositionSnapshotReadReport, read_real_testnet_position_snapshot


load_dotenv()

__test__ = False


ReadOnlyEvidenceStatus = Literal["PASS", "WARN", "FAIL"]


class ReadOnlyTestnetEvidenceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_dir: Path = Path("artifacts/testnet_readonly")

    symbol: str = "BTCUSDT"
    require_real_mode: bool = False
    require_no_live_flags: bool = True
    require_account_pass: bool = True
    require_position_pass: bool = True
    require_open_orders_pass: bool = True
    require_final_flat: bool = True
    allow_open_orders: bool = False


class ReadOnlyTestnetEvidenceReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "readonly_testnet_evidence_report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: ReadOnlyEvidenceStatus
    passed: bool

    symbol: str
    simulated: bool
    account_read_passed: bool
    position_read_passed: bool
    open_orders_read_passed: bool
    final_flat: bool
    open_orders_count: int

    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    credential_check: dict[str, Any]
    account_read: dict[str, Any]
    position_read: dict[str, Any]
    open_orders_read: dict[str, Any]
    config: dict[str, Any]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_readonly_testnet_evidence_config() -> ReadOnlyTestnetEvidenceConfig:
    return ReadOnlyTestnetEvidenceConfig(
        output_dir=Path(os.getenv("TESTNET_READONLY_EVIDENCE_OUTPUT_DIR", "artifacts/testnet_readonly")),
        symbol=os.getenv("TESTNET_READONLY_SYMBOL", "BTCUSDT"),
        require_real_mode=env_bool("TESTNET_READONLY_REQUIRE_REAL_MODE", False),
        require_no_live_flags=env_bool("TESTNET_READONLY_REQUIRE_NO_LIVE_FLAGS", True),
        require_account_pass=env_bool("TESTNET_READONLY_REQUIRE_ACCOUNT_PASS", True),
        require_position_pass=env_bool("TESTNET_READONLY_REQUIRE_POSITION_PASS", True),
        require_open_orders_pass=env_bool("TESTNET_READONLY_REQUIRE_OPEN_ORDERS_PASS", True),
        require_final_flat=env_bool("TESTNET_READONLY_REQUIRE_FINAL_FLAT", True),
        allow_open_orders=env_bool("TESTNET_READONLY_ALLOW_OPEN_ORDERS", False),
    )


def build_readonly_testnet_evidence_report(
    *,
    credential_check: RealTestnetCredentialCheckReport | dict[str, Any],
    account_read: RealAccountSnapshotReadReport | dict[str, Any],
    position_read: RealPositionSnapshotReadReport | dict[str, Any],
    open_orders_read: RealOpenOrdersReadReport | dict[str, Any],
    config: ReadOnlyTestnetEvidenceConfig | None = None,
) -> ReadOnlyTestnetEvidenceReport:
    resolved_config = config or load_readonly_testnet_evidence_config()

    credentials = (
        credential_check
        if isinstance(credential_check, RealTestnetCredentialCheckReport)
        else RealTestnetCredentialCheckReport.model_validate(credential_check)
    )
    account = (
        account_read
        if isinstance(account_read, RealAccountSnapshotReadReport)
        else RealAccountSnapshotReadReport.model_validate(account_read)
    )
    position = (
        position_read
        if isinstance(position_read, RealPositionSnapshotReadReport)
        else RealPositionSnapshotReadReport.model_validate(position_read)
    )
    open_orders = (
        open_orders_read
        if isinstance(open_orders_read, RealOpenOrdersReadReport)
        else RealOpenOrdersReadReport.model_validate(open_orders_read)
    )

    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if not credentials.passed:
        blockers.append("credential_check_not_passed")
        blockers.extend([f"credential:{item}" for item in credentials.blockers])

    if resolved_config.require_account_pass and not account.passed:
        blockers.append("account_read_not_passed")
        blockers.extend([f"account:{item}" for item in account.blockers])

    if resolved_config.require_position_pass and not position.passed:
        blockers.append("position_read_not_passed")
        blockers.extend([f"position:{item}" for item in position.blockers])

    if resolved_config.require_open_orders_pass and not open_orders.passed:
        blockers.append("open_orders_read_not_passed")
        blockers.extend([f"open_orders:{item}" for item in open_orders.blockers])

    if resolved_config.require_final_flat and not position.flat:
        blockers.append("final_position_not_flat")

    if not resolved_config.allow_open_orders and open_orders.open_orders_count > 0:
        blockers.append("open_orders_present_in_readonly_validation")

    simulated = (
        credentials.adapter_simulate
        or account.simulated
        or position.simulated
        or open_orders.simulated
    )

    if resolved_config.require_real_mode and simulated:
        blockers.append("real_mode_required_but_one_or_more_reads_are_simulated")

    warnings.extend([f"credential:{item}" for item in credentials.warnings])
    warnings.extend([f"account:{item}" for item in account.warnings])
    warnings.extend([f"position:{item}" for item in position.warnings])
    warnings.extend([f"open_orders:{item}" for item in open_orders.warnings])

    if simulated:
        warnings.append("readonly_validation_is_simulated")
        recommendations.append("Para validação real, usar BINANCE_TESTNET_SIMULATE=false e API key/secret da testnet.")

    recommendations.append("Read-only aprovado não autoriza envio de ordem.")
    recommendations.append("Avançar para ordem testnet somente após evidence report PASS sem live flags.")

    passed = not blockers

    return ReadOnlyTestnetEvidenceReport(
        status="PASS" if passed and not warnings else "WARN" if passed else "FAIL",
        passed=passed,
        symbol=resolved_config.symbol,
        simulated=simulated,
        account_read_passed=account.passed,
        position_read_passed=position.passed,
        open_orders_read_passed=open_orders.passed,
        final_flat=position.flat,
        open_orders_count=open_orders.open_orders_count,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=sorted(set(recommendations)),
        credential_check=credentials.model_dump(mode="json"),
        account_read=account.model_dump(mode="json"),
        position_read=position.model_dump(mode="json"),
        open_orders_read=open_orders.model_dump(mode="json"),
        config=resolved_config.model_dump(mode="json"),
    )


def run_readonly_testnet_validation(
    *,
    symbol: str | None = None,
    config: ReadOnlyTestnetEvidenceConfig | None = None,
) -> ReadOnlyTestnetEvidenceReport:
    resolved_config = config or load_readonly_testnet_evidence_config()
    resolved_symbol = symbol or resolved_config.symbol

    credentials = evaluate_real_testnet_credential_check(
    config=RealTestnetCredentialCheckConfig(
        require_real_mode=resolved_config.require_real_mode,
        require_no_live_flags=resolved_config.require_no_live_flags,
    )
)
    account = read_real_testnet_account_snapshot(symbol=resolved_symbol)
    position = read_real_testnet_position_snapshot(
        symbol=resolved_symbol,
        require_flat=resolved_config.require_final_flat,
    )
    open_orders = read_real_testnet_open_orders(
        symbol=resolved_symbol,
        allow_open_orders=resolved_config.allow_open_orders,
    )

    return build_readonly_testnet_evidence_report(
        credential_check=credentials,
        account_read=account,
        position_read=position,
        open_orders_read=open_orders,
        config=resolved_config.model_copy(update={"symbol": resolved_symbol}),
    )


def export_readonly_testnet_evidence_report(
    report: ReadOnlyTestnetEvidenceReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "readonly_testnet_evidence_report",
) -> Path:
    config = load_readonly_testnet_evidence_config()
    path = Path(output_dir or config.output_dir)
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{name}.json"
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path