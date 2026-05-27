from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config_management.feature_flags import (
    FeatureFlagContext,
    build_default_feature_flags,
    evaluate_feature_flags,
    export_feature_flags,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run feature flags demo.")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--path", default="artifacts/config/feature_flags_demo.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    flags = build_default_feature_flags()
    context = FeatureFlagContext(environment="development", symbol="BTCUSDT", session_id="demo")
    report = evaluate_feature_flags(flags=flags, context=context)

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), flush=True)

    if args.export:
        path = export_feature_flags(flags, path=args.path)
        print(f"Feature flags exported: {path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())