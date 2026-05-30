from __future__ import annotations
from binance_testnet_adapter.sanitization import sanitize_artifact_payload
import os
from pathlib import Path

from binance_testnet_adapter.order_submit import (
    BinanceTestnetOrderSubmitRequest,
    BinanceTestnetOrderSubmitReport,
    submit_binance_testnet_order,
)
from binance_testnet_adapter.signed_client import load_binance_testnet_adapter_config
from testnet_order_lifecycle.lifecycle_models import (
    TestnetOrderLifecycleConfig,
    export_lifecycle_json,
    load_testnet_order_lifecycle_config,
    validate_lifecycle_config,
)


def validate_real_testnet_test_order(
    *,
    config: TestnetOrderLifecycleConfig | None = None,
) -> BinanceTestnetOrderSubmitReport:
    resolved = config or load_testnet_order_lifecycle_config()
    blockers = validate_lifecycle_config(resolved)

    if blockers:
        return BinanceTestnetOrderSubmitReport(
            status="BLOCKED",
            passed=False,
            submitted=False,
            dry_run=True,
            simulated=resolved.simulate,
            request={
                "symbol": resolved.symbol,
                "side": resolved.side,
                "order_type": "LIMIT",
                "quantity": resolved.quantity,
                "price": resolved.price,
            },
            blockers=blockers,
            warnings=[],
            config=resolved.model_dump(mode="json"),
        )

    base_adapter_config = load_binance_testnet_adapter_config()
    adapter_config = base_adapter_config.model_copy(
        update={
            "simulate": resolved.simulate,
            "allow_order_submission": False,
            "allow_cancel_orders": False,
        }
    )

    return submit_binance_testnet_order(
        request=BinanceTestnetOrderSubmitRequest(
            symbol=resolved.symbol,
            side=resolved.side,
            order_type="LIMIT",
            quantity=resolved.quantity,
            price=resolved.price,
            time_in_force=resolved.time_in_force,
            dry_run=True,
            validate_on_exchange=True,
        ),
        config=adapter_config,
    )


def export_test_order_validation_report(
    report: BinanceTestnetOrderSubmitReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_test_order_validation",
) -> Path:
    return export_lifecycle_json(
        report,
        output_dir=output_dir
        or os.getenv(
            "TESTNET_ORDER_LIFECYCLE_TEST_ORDER_OUTPUT_DIR",
            "artifacts/testnet_order_lifecycle",
        ),
        name=name,
    )