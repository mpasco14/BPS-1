from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from testnet_readonly.account_read import (
    export_real_testnet_account_snapshot_read_report,
    read_real_testnet_account_snapshot,
)
from testnet_readonly.credential_check import (
    evaluate_real_testnet_credential_check,
    export_real_testnet_credential_check_report,
)
from testnet_readonly.open_orders_read import (
    export_real_testnet_open_orders_read_report,
    read_real_testnet_open_orders,
)
from testnet_readonly.position_read import (
    export_real_testnet_position_snapshot_read_report,
    read_real_testnet_position_snapshot,
)
from testnet_readonly.readonly_evidence_report import (
    build_readonly_testnet_evidence_report,
    export_readonly_testnet_evidence_report,
    load_readonly_testnet_evidence_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real/simulated testnet read-only validation.")

    parser.add_argument("--symbol", default=None)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/testnet_readonly")
    parser.add_argument("--name", default="real_testnet_readonly_validation")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    config = load_readonly_testnet_evidence_config()
    symbol = args.symbol or config.symbol

    credentials = evaluate_real_testnet_credential_check()
    account = read_real_testnet_account_snapshot(symbol=symbol)
    position = read_real_testnet_position_snapshot(
        symbol=symbol,
        require_flat=config.require_final_flat,
    )
    open_orders = read_real_testnet_open_orders(
        symbol=symbol,
        allow_open_orders=config.allow_open_orders,
    )

    evidence = build_readonly_testnet_evidence_report(
        credential_check=credentials,
        account_read=account,
        position_read=position,
        open_orders_read=open_orders,
        config=config.model_copy(update={"symbol": symbol}),
    )

    print(json.dumps(evidence.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        output_dir.mkdir(parents=True, exist_ok=True)

        export_real_testnet_credential_check_report(
            credentials,
            output_dir=output_dir,
            name=f"{args.name}_credential_check",
        )
        export_real_testnet_account_snapshot_read_report(
            account,
            output_dir=output_dir,
            name=f"{args.name}_account_snapshot",
        )
        export_real_testnet_position_snapshot_read_report(
            position,
            output_dir=output_dir,
            name=f"{args.name}_position_snapshot",
        )
        export_real_testnet_open_orders_read_report(
            open_orders,
            output_dir=output_dir,
            name=f"{args.name}_open_orders",
        )
        export_readonly_testnet_evidence_report(
            evidence,
            output_dir=output_dir,
            name=f"{args.name}_evidence",
        )

        print(f"Read-only testnet artifacts exported to: {output_dir}", flush=True)

    return 0 if evidence.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())