from __future__ import annotations

import os
from pathlib import Path

from binance_testnet_adapter.order_cancel import (
    BinanceTestnetCancelOrderRequest,
    BinanceTestnetCancelOrderReport,
    cancel_binance_testnet_order,
)
from binance_testnet_adapter.signed_client import (
    load_binance_testnet_adapter_config,
)
from testnet_order_lifecycle.lifecycle_models import (
    TestnetOrderLifecycleConfig,
    export_lifecycle_json,
    load_testnet_order_lifecycle_config,
)


def cancel_real_testnet_order(
    *,
    client_order_id: str | None = None,
    order_id: int | None = None,
    config: TestnetOrderLifecycleConfig | None = None,
) -> BinanceTestnetCancelOrderReport:
    resolved = config or load_testnet_order_lifecycle_config()

    base_adapter_config = load_binance_testnet_adapter_config()
    adapter_config = base_adapter_config.model_copy(
        update={
            "simulate": resolved.simulate,
            "allow_order_submission": resolved.allow_real_submit,
            "allow_cancel_orders": resolved.allow_real_cancel,
        }
    )
    return cancel_binance_testnet_order(
        request=BinanceTestnetCancelOrderRequest(
            symbol=resolved.symbol,
            order_id=order_id,
            orig_client_order_id=client_order_id,
        ),
        config=adapter_config,
    )


def export_cancel_order_report(
    report: BinanceTestnetCancelOrderReport,
    *,
    output_dir: str | Path | None = None,
    name: str = "real_testnet_cancel_order",
) -> Path:
    return export_lifecycle_json(
        report,
        output_dir=output_dir or os.getenv("TESTNET_ORDER_LIFECYCLE_CANCEL_OUTPUT_DIR", "artifacts/testnet_order_lifecycle"),
        name=name,
    )