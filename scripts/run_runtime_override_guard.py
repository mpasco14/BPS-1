from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config_management.runtime_override_guard import (
    RuntimeOverrideRequest,
    evaluate_runtime_override,
    export_runtime_override_decision,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run runtime override guard demo.")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/config")
    parser.add_argument("--name", default="runtime_override_decision_demo")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    decision = evaluate_runtime_override(
        request=RuntimeOverrideRequest(
            override_id="demo_override",
            key="strategy.min_confidence",
            old_value=0.65,
            new_value=0.62,
            reason="Demo adjustment for paper testing.",
            environment="development",
            ttl_minutes=15,
        )
    )

    print(json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_runtime_override_decision(decision, output_dir=args.output_dir, name=args.name)
        print(f"Runtime override decision exported: {path}", flush=True)

    return 0 if decision.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())